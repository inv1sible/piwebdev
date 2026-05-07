#!/usr/bin/env python3
"""
Minimal exec bridge — runs commands on the host and returns JSON output.
Accepts one JSON line per connection: {"cmd": [...], "cwd": "...", "timeout": 30}
Returns one JSON line: {"ok": bool, "stdout": "...", "stderr": "...", "code": N}
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path

SOCKET_PATH = os.environ.get("EXEC_BRIDGE_SOCKET", "/var/opt/piwebdev/exec-bridge.sock")


async def handle_client(reader, writer):
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not line:
            return
        req = json.loads(line.decode())
        cmd = req.get("cmd", [])
        cwd = req.get("cwd", "/")
        timeout = int(req.get("timeout", 30))

        if not cmd or not isinstance(cmd, list):
            resp = {"ok": False, "stdout": "", "stderr": "invalid command", "code": -1}
        elif not os.path.isdir(cwd):
            resp = {"ok": False, "stdout": "", "stderr": f"cwd not found: {cwd}", "code": -1}
        else:
            try:
                p = subprocess.run(
                    cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout
                )
                resp = {
                    "ok": p.returncode == 0,
                    "stdout": p.stdout,
                    "stderr": p.stderr,
                    "code": p.returncode,
                }
            except subprocess.TimeoutExpired:
                resp = {"ok": False, "stdout": "", "stderr": "command timed out", "code": -1}
            except FileNotFoundError as e:
                resp = {"ok": False, "stdout": "", "stderr": str(e), "code": -1}

        writer.write((json.dumps(resp) + "\n").encode())
        await writer.drain()
    except Exception as e:
        try:
            writer.write((json.dumps({"ok": False, "stdout": "", "stderr": str(e), "code": -1}) + "\n").encode())
            await writer.drain()
        except Exception:
            pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    sock = Path(SOCKET_PATH)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(handle_client, str(sock))
    os.chmod(str(sock), 0o666)
    print(f"[exec-bridge] listening on {sock}", flush=True)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
