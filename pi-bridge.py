#!/usr/bin/env python3
"""
pi-bridge: Unix socket server that proxies pi --mode rpc sessions to Docker clients.

Protocol:
  1. Client connects to SOCKET_PATH
  2. Client sends one JSON line: {"args": ["--session-dir", "...", ...], "cwd": "/path"}
  3. Bridge spawns: pi --mode rpc <args> with the given cwd
  4. Raw JSONL is proxied bidirectionally (client stdin → pi stdin, pi stdout → client)
  5. Pi stderr is logged to bridge stderr
  6. Client disconnect → pi receives SIGTERM
"""
import asyncio
import json
import os
import sys
from pathlib import Path

SOCKET_PATH = os.environ.get("PI_BRIDGE_SOCKET", "/var/opt/piwebdev/pi-bridge.sock")
PI_BIN = os.environ.get("PI_BIN", "/home/user01/.nvm/versions/node/v20.20.2/bin/pi")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername") or "client"
    proc = None
    try:
        init_line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not init_line:
            return
        init = json.loads(init_line.decode())
        args = init.get("args", [])
        cwd = init.get("cwd", "/")

        env = os.environ.copy()
        env["HOME"] = str(Path.home())

        proc = await asyncio.create_subprocess_exec(
            PI_BIN, *args,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        print(f"[pi-bridge] session started pid={proc.pid} cwd={cwd}", flush=True)

        async def pipe_in():
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    proc.stdin.write(data)
                    await proc.stdin.drain()
            except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

        async def pipe_out():
            try:
                while not proc.stdout.at_eof():
                    data = await proc.stdout.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
                pass

        async def log_stderr():
            try:
                while not proc.stderr.at_eof():
                    line = await proc.stderr.readline()
                    if line:
                        print(f"[pi stderr] {line.decode(errors='replace').rstrip()}", flush=True)
            except Exception:
                pass

        await asyncio.gather(pipe_in(), pipe_out(), log_stderr())

    except asyncio.TimeoutError:
        print("[pi-bridge] client timed out waiting for init", flush=True)
    except Exception as e:
        print(f"[pi-bridge] error: {e}", file=sys.stderr, flush=True)
    finally:
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
            print(f"[pi-bridge] session ended pid={proc.pid}", flush=True)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    sock = Path(SOCKET_PATH)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(handle_client, str(sock))
    sock.chmod(0o666)
    print(f"[pi-bridge] listening on {sock}", flush=True)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
