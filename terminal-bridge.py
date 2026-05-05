#!/usr/bin/env python3
"""
PTY terminal bridge with persistent sessions.

Each session_id keeps its shell alive after the client disconnects.
The next client connecting with the same session_id resumes the shell.
"""
import asyncio
import base64
import fcntl
import json
import os
import pty
import pwd
import signal
import struct
import subprocess
import termios
from pathlib import Path

SOCKET_PATH = os.environ.get("TERMINAL_BRIDGE_SOCKET", "/var/opt/piwebdev/terminal-bridge.sock")
SHELL        = os.environ.get("TERMINAL_SHELL",          "/bin/bash")
IDLE_TIMEOUT = int(os.environ.get("TERMINAL_IDLE_TIMEOUT",  "1800"))  # kill shell after this many idle seconds
LINGER       = int(os.environ.get("TERMINAL_LINGER",         "300"))   # keep shell alive this long after disconnect
MAX_CLIENTS  = int(os.environ.get("TERMINAL_MAX_SESSIONS",    "4"))    # max simultaneous connected clients

# Persistent session store (keyed by Django TerminalSession PK)
# Each entry: {"master_fd": int, "proc": Popen, "in_use": bool}
_sessions: dict = {}
_orphan_tasks: dict = {}   # session_id -> asyncio.Task (linger/idle watcher)
_active_clients = 0        # currently connected clients


def _set_winsize(fd, cols, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _destroy_session(session_id, loop):
    """Kill the shell and remove the session from the store."""
    s = _sessions.pop(session_id, None)
    _orphan_tasks.pop(session_id, None)
    if s is None:
        return
    try:
        loop.remove_reader(s["master_fd"])
    except Exception:
        pass
    try:
        os.close(s["master_fd"])
    except OSError:
        pass
    try:
        s["proc"].terminate()
    except Exception:
        pass
    print(f"[terminal-bridge] session {session_id} destroyed", flush=True)


async def handle_client(reader, writer):
    global _active_clients
    loop = asyncio.get_running_loop()

    def log(msg):
        print(f"[terminal-bridge] {msg}", flush=True)

    if _active_clients >= MAX_CLIENTS:
        writer.write((json.dumps({"t": "err", "msg": "max sessions reached"}) + "\n").encode())
        await writer.drain()
        writer.close()
        return

    _active_clients += 1

    master_fd = None
    proc      = None
    idle_task = None
    session_id = None
    reused     = False

    try:
        # ── Read init JSON ────────────────────────────────────────
        try:
            init_line = await asyncio.wait_for(reader.readline(), timeout=10)
        except asyncio.TimeoutError:
            return
        if not init_line:
            return

        init       = json.loads(init_line.decode())
        cols       = max(10, int(init.get("cols", 80)))
        rows       = max(5,  int(init.get("rows", 24)))
        cwd        = init.get("cwd", str(Path.home()))
        session_id = init.get("session_id")
        if not os.path.isdir(cwd):
            cwd = str(Path.home())

        # ── Try to reuse existing session ─────────────────────────
        if session_id and session_id in _sessions:
            s = _sessions[session_id]
            if s["in_use"]:
                writer.write((json.dumps({"t": "err", "msg": "session already in use"}) + "\n").encode())
                await writer.drain()
                return
            if s["proc"].poll() is None:   # shell still running
                master_fd = s["master_fd"]
                proc      = s["proc"]
                s["in_use"] = True
                reused = True
                # Cancel the linger/idle watcher
                t = _orphan_tasks.pop(session_id, None)
                if t:
                    t.cancel()
                log(f"resumed session {session_id} pid={proc.pid}")
            else:
                # Shell died while we were away — clean up and start fresh
                _destroy_session(session_id, loop)

        # ── Create new shell if not reusing ───────────────────────
        if not reused:
            master_fd, slave_fd = pty.openpty()
            _set_winsize(master_fd, cols, rows)

            pw = pwd.getpwuid(os.getuid())
            env = {
                "TERM": "xterm-256color",
                "COLORTERM": "truecolor",
                "HOME":    pw.pw_dir,
                "USER":    pw.pw_name,
                "LOGNAME": pw.pw_name,
                "SHELL":   SHELL,
                "LANG":    "en_US.UTF-8",
                "PATH":    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin",
            }

            def preexec():
                os.setsid()
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)   # needed for sudo prompts

            proc = subprocess.Popen(
                [SHELL, "--login"],
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                close_fds=True, preexec_fn=preexec, env=env, cwd=cwd,
            )
            os.close(slave_fd)

            if session_id:
                _sessions[session_id] = {"master_fd": master_fd, "proc": proc, "in_use": True}
            log(f"new session {session_id} pid={proc.pid} cols={cols} rows={rows}")

        # Apply (possibly new) terminal size
        _set_winsize(master_fd, cols, rows)

        # Notify client: resumed or connected
        status_msg = "resumed" if reused else "connected"
        writer.write((json.dumps({"t": "status", "msg": status_msg}) + "\n").encode())
        await writer.drain()

        # On resume, send SIGWINCH so bash/vim/etc redraw the screen
        if reused:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGWINCH)
            except (OSError, ProcessLookupError):
                pass

        # ── Bidirectional proxy ───────────────────────────────────
        last_activity = loop.time()

        def reset_idle():
            nonlocal last_activity
            last_activity = loop.time()

        pty_q: asyncio.Queue = asyncio.Queue(maxsize=512)

        def pty_readable():
            try:
                data = os.read(master_fd, 65536)
                if data:
                    reset_idle()
                    frame = (json.dumps({"t": "d", "d": base64.b64encode(data).decode()}) + "\n").encode()
                    try:
                        pty_q.put_nowait(frame)
                    except asyncio.QueueFull:
                        pass
            except OSError:
                loop.remove_reader(master_fd)
                try:
                    pty_q.put_nowait(None)
                except asyncio.QueueFull:
                    pass

        loop.add_reader(master_fd, pty_readable)

        async def idle_watcher():
            while True:
                await asyncio.sleep(30)
                if loop.time() - last_activity > IDLE_TIMEOUT:
                    log(f"idle timeout — killing session {session_id}")
                    _destroy_session(session_id, loop)
                    break

        idle_task = asyncio.create_task(idle_watcher())

        async def send_output():
            try:
                while True:
                    item = await pty_q.get()
                    if item is None:
                        break
                    writer.write(item)
                    await writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

        async def recv_input():
            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    reset_idle()
                    try:
                        msg = json.loads(line.decode())
                    except Exception:
                        continue
                    t = msg.get("t")
                    if t == "d":
                        try:
                            os.write(master_fd, base64.b64decode(msg["d"]))
                        except OSError:
                            break
                    elif t == "r":
                        try:
                            nc, nr = int(msg.get("c", cols)), int(msg.get("r", rows))
                            _set_winsize(master_fd, nc, nr)
                            os.killpg(os.getpgid(proc.pid), signal.SIGWINCH)
                        except (OSError, ProcessLookupError):
                            pass
            except (asyncio.CancelledError, ConnectionResetError):
                pass

        send_task = asyncio.create_task(send_output())
        recv_task = asyncio.create_task(recv_input())
        done, pending = await asyncio.wait([send_task, recv_task], return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    except Exception as e:
        log(f"error: {e}")
    finally:
        if idle_task:
            idle_task.cancel()

        # Stop reading PTY (we'll re-add it on the next client connection)
        if master_fd is not None:
            try:
                loop.remove_reader(master_fd)
            except Exception:
                pass

        if session_id and session_id in _sessions:
            _sessions[session_id]["in_use"] = False
            if proc and proc.poll() is not None:
                # Shell died
                _destroy_session(session_id, loop)
            else:
                # Shell alive — keep it for LINGER seconds, then destroy
                async def linger_watcher(sid=session_id):
                    await asyncio.sleep(LINGER)
                    if sid in _sessions and not _sessions[sid]["in_use"]:
                        log(f"session {sid} lingered — destroying")
                        _destroy_session(sid, loop)
                _orphan_tasks[session_id] = asyncio.create_task(linger_watcher())
                log(f"session {session_id} disconnected — shell persists for {LINGER}s")
        elif proc and not reused:
            # No session tracking — kill directly
            try:
                proc.terminate()
            except Exception:
                pass

        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        _active_clients -= 1
        log(f"client disconnected (active={_active_clients})")


async def main():
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)   # auto-reap zombie children

    sock = Path(SOCKET_PATH)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(handle_client, str(sock))
    os.chmod(str(sock), 0o666)
    print(f"[terminal-bridge] listening on {sock}", flush=True)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
