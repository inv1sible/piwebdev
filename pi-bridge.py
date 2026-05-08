#!/usr/bin/env python3
"""
pi-bridge: Unix socket server with persistent pi sessions.

Each session is keyed by session_dir. When a client (WebSocket consumer)
disconnects mid-task, the pi process keeps running and its output is
buffered. The next client with the same session_key receives the buffered
events + live stream without losing anything.

Protocol — init line from client:
  {"args": [...], "cwd": "...", "session_key": "/path/to/session-dir"}

First response line from bridge:
  {"status": "started"}                       — new pi session
  {"status": "resuming", "buffered": N}       — existing session, N lines to replay
  {"status": "busy"}                          — session already has a client
  {"status": "error", "message": "..."}       — spawn failed

Then: raw JSONL events from pi stdout. Client writes JSON prompts to stdin.

On client disconnect: pi keeps running for PI_LINGER seconds, then SIGTERM.
"""
import asyncio
import collections
import json
import os
import sys
from pathlib import Path

SOCKET_PATH = os.environ.get("PI_BRIDGE_SOCKET", "/var/opt/piwebdev/pi-bridge.sock")
PI_BIN      = os.environ.get("PI_BIN",      "/home/user01/.nvm/versions/node/v20.20.2/bin/pi")
LINGER      = int(os.environ.get("PI_LINGER",   "600"))   # seconds to keep pi alive after disconnect
MAX_BUF     = int(os.environ.get("PI_MAX_BUF",  "2000"))  # max lines buffered while disconnected


class PiSession:
    """State for one persistent pi RPC session."""
    __slots__ = ("proc", "session_key", "buf", "live_queue", "in_use",
                 "linger_task", "stdout_task", "stderr_task")

    def __init__(self, proc, session_key: str):
        self.proc        = proc
        self.session_key = session_key
        self.buf         = collections.deque(maxlen=MAX_BUF)  # lines buffered while no client
        self.live_queue  = None   # asyncio.Queue when a client is attached
        self.in_use      = False
        self.linger_task = None
        self.stdout_task = None
        self.stderr_task = None


# Global session store keyed by session_key (= session_dir path)
_sessions: dict[str, PiSession] = {}


# ── Background drain tasks ─────────────────────────────────────────────────────

async def _drain_stdout(session: PiSession):
    """
    Read pi stdout continuously.
    - When a client is attached (live_queue is set): push to queue.
    - When no client:                                push to buffer.
    Either way the line is never lost.
    """
    try:
        while not session.proc.stdout.at_eof():
            line = await session.proc.stdout.readline()
            if not line:
                break
            q = session.live_queue
            if q is not None:
                try:
                    q.put_nowait(line)
                except asyncio.QueueFull:
                    session.buf.append(line)  # fallback: buffer if queue full
            else:
                session.buf.append(line)
    except Exception:
        pass
    finally:
        # Signal EOF to any attached client
        q = session.live_queue
        if q is not None:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        _sessions.pop(session.session_key, None)
        _log(f"session {session.session_key!r} stdout closed (pid={session.proc.pid})")
        # Terminate process if stdout closed but process is still alive (e.g. pi crashed stdout but didn't exit)
        if session.proc.returncode is None:
            try:
                session.proc.terminate()
            except Exception:
                pass


async def _drain_stderr(session: PiSession):
    try:
        while not session.proc.stderr.at_eof():
            line = await session.proc.stderr.readline()
            if line:
                print(f"[pi stderr] {line.decode(errors='replace').rstrip()}", flush=True)
    except Exception:
        pass


# ── Session lifecycle ──────────────────────────────────────────────────────────

def _log(msg: str):
    print(f"[pi-bridge] {msg}", flush=True)


def _cancel_linger(session: PiSession):
    if session.linger_task:
        session.linger_task.cancel()
        session.linger_task = None


def _terminate_session(session: PiSession):
    _sessions.pop(session.session_key, None)
    _cancel_linger(session)
    if session.stdout_task:
        session.stdout_task.cancel()
    if session.stderr_task:
        session.stderr_task.cancel()
    if session.proc.returncode is None:
        try:
            session.proc.terminate()
        except Exception:
            pass
    _log(f"session {session.session_key!r} terminated (pid={session.proc.pid})")


def _start_linger(session: PiSession):
    _cancel_linger(session)

    async def _wait(s: PiSession = session):
        await asyncio.sleep(LINGER)
        if _sessions.get(s.session_key) is s and not s.in_use:
            _log(f"session {s.session_key!r} linger expired — terminating")
            _terminate_session(s)

    session.linger_task = asyncio.create_task(_wait())
    _log(f"session {session.session_key!r} client detached — pi persists for {LINGER}s")


# ── Client handler ─────────────────────────────────────────────────────────────

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    def reply(obj: dict):
        writer.write((json.dumps(obj) + "\n").encode())

    # ── Read init ──────────────────────────────────────────────────────────────
    try:
        init_line = await asyncio.wait_for(reader.readline(), timeout=10)
        init = json.loads(init_line.decode())
    except Exception as e:
        _log(f"init error: {e}")
        try:
            writer.close()
        except Exception:
            pass
        return

    args        = init.get("args", [])
    cwd         = init.get("cwd", "/")
    session_key = init.get("session_key")

    session = None
    resumed = False

    # ── Try to reattach to existing session ────────────────────────────────────
    if session_key and session_key in _sessions:
        s = _sessions[session_key]
        if s.in_use:
            reply({"status": "busy"})
            await writer.drain()
            writer.close()
            return
        if s.proc.returncode is None:   # pi still running
            session = s
            resumed = True
            _cancel_linger(s)
            _log(f"resuming session {session_key!r} pid={s.proc.pid}")
        else:
            # Pi exited while we were away — discard and start fresh
            _sessions.pop(session_key, None)

    # ── Start new pi process ───────────────────────────────────────────────────
    if not resumed:
        env = os.environ.copy()
        env["HOME"] = str(Path.home())
        try:
            proc = await asyncio.create_subprocess_exec(
                PI_BIN, *args,
                cwd=cwd, env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            reply({"status": "error", "message": str(e)})
            await writer.drain()
            writer.close()
            return

        session = PiSession(proc, session_key or "")
        if session_key:
            _sessions[session_key] = session
        session.stdout_task = asyncio.create_task(_drain_stdout(session))
        session.stderr_task = asyncio.create_task(_drain_stderr(session))
        _log(f"new session {session_key!r} pid={proc.pid}")

    session.in_use = True

    # ── Send handshake + replay buffer (atomically: snapshot then set queue) ───
    if resumed:
        # Snapshot BEFORE setting live_queue — no await between, so no race
        replay_snapshot = list(session.buf)
        session.buf.clear()
        session.live_queue = asyncio.Queue(maxsize=1000)

        reply({"status": "resuming", "buffered": len(replay_snapshot)})
        await writer.drain()

        for line in replay_snapshot:
            writer.write(line)
        if replay_snapshot:
            await writer.drain()
    else:
        session.live_queue = asyncio.Queue(maxsize=1000)
        reply({"status": "started"})
        await writer.drain()

    # ── Bidirectional relay ────────────────────────────────────────────────────

    async def relay_stdin():
        """Client → pi stdin.

        The web UI's Stop button sends a JSONL {"type":"abort"} frame. Treat
        that as a hard stop for the persistent pi process/session; forwarding it
        blindly is not reliable across pi versions/providers and can leave the
        browser stuck in a working state.
        """
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                try:
                    msg = json.loads(data.decode())
                except Exception:
                    msg = None
                if isinstance(msg, dict) and msg.get("type") == "abort":
                    _log(f"abort requested for session {session.session_key!r} pid={session.proc.pid}")
                    _terminate_session(session)
                    break
                if not session.proc.stdin.is_closing():
                    session.proc.stdin.write(data)
                    await session.proc.stdin.drain()
        except Exception:
            pass

    async def relay_stdout():
        """Live queue → client."""
        try:
            while True:
                item = await session.live_queue.get()
                if item is None:
                    break
                writer.write(item)
                await writer.drain()
        except Exception:
            pass

    stdin_task  = asyncio.create_task(relay_stdin())
    stdout_task = asyncio.create_task(relay_stdout())

    done, pending = await asyncio.wait(
        [stdin_task, stdout_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    # ── Detach client ──────────────────────────────────────────────────────────
    session.live_queue = None
    session.in_use     = False

    if session_key and session_key in _sessions:
        if session.proc.returncode is None:
            _start_linger(session)
        else:
            _sessions.pop(session_key, None)
    elif not session_key and session.proc.returncode is None:
        # Untracked session (no session_key) — terminate immediately
        try:
            session.proc.terminate()
        except Exception:
            pass

    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    sock = Path(SOCKET_PATH)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(handle_client, str(sock))
    sock.chmod(0o666)
    _log(f"listening on {sock} (linger={LINGER}s, max_buf={MAX_BUF})")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
