import asyncio
import json
import os
import shlex
from pathlib import Path
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.utils import timezone
from .models import PiSession, ChatMessage, UserPiSettings, ProjectPiSettings, TerminalSession


class PiConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self._pi_reader = None
        self._pi_writer = None
        self.session = None
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session = await self.get_session()
        if not self.session:
            await self.close(code=4404)
            return
        await self.accept()
        await self.send_json({"type": "status", "message": "connected"})
        await self.start_pi()

    async def disconnect(self, code):
        if self._pi_writer and not self._pi_writer.is_closing():
            self._pi_writer.close()
            try:
                await asyncio.wait_for(self._pi_writer.wait_closed(), timeout=3)
            except (asyncio.TimeoutError, Exception):
                pass
        if self.session:
            await self.mark_stopped()

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except Exception:
            return
        if data.get("type") == "prompt":
            msg = (data.get("message") or "").strip()
            if not msg:
                return
            await self.store_message("user", msg)
            await self.send_json({"type": "message", "role": "user", "content": msg})
            payload = {"type": "prompt", "message": await self.build_prompt(msg), "streamingBehavior": "followUp"}
            await self.write_pi(payload)
        elif data.get("type") == "checkpoint":
            label = (data.get("label") or "").strip()[:80] or "Checkpoint"
            await self.store_message("system", label, {"type": "checkpoint"})
            await self.send_json({"type": "checkpoint", "label": label})
        elif data.get("type") == "abort":
            await self.send_json({"type": "status", "message": "stopping…", "working": True})
            await self.write_pi({"type": "abort"})

    async def start_pi(self):
        cfg = await self.resolve_settings()
        session_dir = await self.ensure_session_dir()
        pi_args = ["--mode", "rpc", "--session-dir", session_dir]
        if any(Path(session_dir).rglob("*.jsonl")):
            pi_args.append("--continue")
        if cfg["provider"]:
            pi_args += ["--provider", cfg["provider"]]
        if cfg["model"]:
            pi_args += ["--model", cfg["model"]]
        if cfg["thinking_level"]:
            pi_args += ["--thinking", cfg["thinking_level"]]
        if cfg["extra_args"]:
            pi_args += shlex.split(cfg["extra_args"])

        bridge_sock = getattr(settings, "PI_BRIDGE_SOCKET", "/var/opt/piwebdev/pi-bridge.sock")
        try:
            self._pi_reader, self._pi_writer = await asyncio.open_unix_connection(bridge_sock)
        except Exception as e:
            await self.send_json({"type": "stderr", "content": f"pi-bridge unavailable: {e}\n"})
            await self.close()
            return

        init = json.dumps({
            "args": pi_args,
            "cwd": self.session.project.path,
            "session_key": session_dir,
        }) + "\n"
        self._pi_writer.write(init.encode())
        await self._pi_writer.drain()

        # Read handshake line from pi-bridge (started / resuming / busy / error)
        try:
            hs_line = await asyncio.wait_for(self._pi_reader.readline(), timeout=30)
            hs = json.loads(hs_line.decode())
        except Exception as e:
            await self.send_json({"type": "stderr", "content": f"pi-bridge handshake failed: {e}\n"})
            await self.close()
            return

        if hs.get("status") == "error":
            await self.send_json({"type": "stderr", "content": hs.get("message", "pi spawn error")})
            await self.close()
            return

        if hs.get("status") == "busy":
            await self.send_json({"type": "stderr", "content": "Another client is already connected to this session. Close the other tab first."})
            await self.close()
            return

        await self.mark_running(cfg)

        replay_count = 0
        if hs.get("status") == "resuming":
            replay_count = hs.get("buffered", 0)
            if replay_count:
                # Buffered events exist — agent was actively working while offline
                await self.send_json({
                    "type": "status",
                    "message": f"resumed — catching up ({replay_count} event{'s' if replay_count != 1 else ''})",
                    "working": True,
                    "model": cfg["model"],
                    "provider": cfg["provider"],
                })
            else:
                # Pi process alive but idle (e.g. followUp mode waiting for next prompt)
                # Reconnect silently — identical to a fresh start
                await self.send_json({
                    "type": "status",
                    "message": "pi ready",
                    "working": False,
                    "cwd": self.session.project.path,
                    "model": cfg["model"],
                    "provider": cfg["provider"],
                })
        else:
            await self.send_json({
                "type": "status",
                "message": "pi ready",
                "working": False,
                "cwd": self.session.project.path,
                "model": cfg["model"],
                "provider": cfg["provider"],
            })

        asyncio.create_task(self.read_stdout(replay_count=replay_count))

    async def read_stdout(self, replay_count: int = 0):
        assistant = ""
        n = 0  # events processed so far
        try:
            while self._pi_reader and not self._pi_reader.at_eof():
                line = await self._pi_reader.readline()
                if not line:
                    break
                is_replay = n < replay_count
                n += 1
                try:
                    event = json.loads(line.decode())
                except Exception:
                    if not is_replay:
                        await self.send_json({"type": "tool", "content": line.decode(errors="replace")})
                    continue

                if not is_replay:
                    await self.send_json({"type": "pi", "event": event})

                t = event.get("type")
                if t == "message_update":
                    d = event.get("assistantMessageEvent") or {}
                    if d.get("type") == "text_delta":
                        delta = d.get("delta", "")
                        assistant += delta
                        if not is_replay:
                            await self.send_json({"type": "assistant_delta", "delta": delta})
                elif t == "agent_end":
                    if assistant.strip():
                        await self.store_message("assistant", assistant, {"final": True})
                        assistant = ""
                    if is_replay:
                        # Task completed while the browser was away
                        await self.send_json({
                            "type": "toast",
                            "message": "Task completed while you were away — results saved.",
                            "toast_type": "ok",
                        })
                    await self.send_json({"type": "status", "message": "idle", "working": False})
                elif t and "tool" in t:
                    # Store tool events — during replay these are events that were never stored
                    await self.store_message("tool", json.dumps(event, indent=2), {"event_type": t, "tool_name": event.get("toolName") or "tool"})
        except Exception:
            pass
        finally:
            await self.send_json({"type": "status", "message": "idle", "working": False})

    async def write_pi(self, payload):
        if self._pi_writer and not self._pi_writer.is_closing():
            self._pi_writer.write((json.dumps(payload) + "\n").encode())
            await self._pi_writer.drain()

    async def send_json(self, data):
        try:
            await self.send(text_data=json.dumps(data))
        except Exception:
            pass

    @database_sync_to_async
    def get_session(self):
        try:
            return PiSession.objects.select_related("project", "user").get(pk=self.session_id, user=self.user)
        except PiSession.DoesNotExist:
            return None

    @database_sync_to_async
    def store_message(self, role, content, metadata=None):
        self.session.last_message_at = timezone.now()
        self.session.save(update_fields=["last_message_at", "updated_at"])
        return ChatMessage.objects.create(session=self.session, role=role, content=content, metadata=metadata or {})

    @database_sync_to_async
    def ensure_session_dir(self):
        root = Path(self.session.project.path) / ".pi-sessions" / str(self.session.id)
        root.mkdir(parents=True, exist_ok=True)
        stored = self.session.session_dir
        if not stored or not Path(stored).is_relative_to(self.session.project.path):
            self.session.session_dir = str(root)
            self.session.save(update_fields=["session_dir", "updated_at"])
        return self.session.session_dir

    @database_sync_to_async
    def resolve_settings(self):
        user_cfg, _ = UserPiSettings.objects.get_or_create(user=self.user)
        project_cfg, _ = ProjectPiSettings.objects.get_or_create(project=self.session.project)
        return {
            "provider": project_cfg.provider or user_cfg.provider or settings.DEFAULT_PI_PROVIDER,
            "model": project_cfg.model or user_cfg.model or settings.DEFAULT_PI_MODEL,
            "thinking_level": project_cfg.thinking_level or user_cfg.thinking_level or settings.DEFAULT_PI_THINKING,
            "mindset": "\n".join(x for x in [user_cfg.mindset, project_cfg.mindset] if x),
            "inject_memory": project_cfg.inject_memory,
            "extra_args": " ".join(x for x in [user_cfg.extra_args, project_cfg.extra_args] if x),
        }

    @database_sync_to_async
    def build_prompt(self, msg):
        cfg = ProjectPiSettings.objects.get_or_create(project=self.session.project)[0]
        parts = []
        # Always inject MEMORY.md — it is the project's persistent context
        memory_file = Path(self.session.project.path) / "MEMORY.md"
        if memory_file.exists():
            memory_content = memory_file.read_text(encoding="utf-8").strip()
        else:
            memory_content = "# General Memory\n\n\n# Todos\n\n\n# Ideas For Later"
        parts.append(
            "Project memory (MEMORY.md in the project root):\n"
            + memory_content
            + "\n\n"
            "IMPORTANT: After successfully completing this task, update MEMORY.md to reflect "
            "what you learned — architecture decisions, conventions, solved problems, gotchas. "
            "This file is committed to git and is your only persistent memory across sessions."
        )
        if cfg.mindset:
            parts.append("Project mindset/flavour:\n" + cfg.mindset)
        parts.append(
            "Workflow — always follow these steps in order before writing any code:\n"
            "1. Understand – Restate the task briefly in your own words to confirm you grasp it.\n"
            "2. Explore – Read the relevant source files. Map what exists before touching anything.\n"
            "3. Clarify – If anything is ambiguous, ask specific questions and STOP. Wait for the user's answers before proceeding.\n"
            "4. Plan – State exactly which files you will change and how.\n"
            "5. Code – Only after steps 1-4 are complete, make the actual edits."
        )
        parts.append("User request:\n" + msg)
        return "\n\n---\n\n".join(parts)

    @database_sync_to_async
    def mark_running(self, cfg):
        self.session.status = "running"
        self.session.provider = cfg["provider"]
        self.session.model = cfg["model"]
        self.session.thinking_level = cfg["thinking_level"]
        self.session.mindset = cfg["mindset"]
        self.session.last_started_at = timezone.now()
        self.session.save()

    @database_sync_to_async
    def mark_stopped(self):
        self.session.status = "stopped"
        self.session.save(update_fields=["status", "updated_at"])


class TerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self._bridge_reader = None
        self._bridge_writer = None
        self._read_task = None
        self.session = None
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        if not await self.check_access():
            await self.close(code=4403)
            return

        self.terminal_id = self.scope["url_route"]["kwargs"]["terminal_id"]
        self.session = await self.get_session()
        if not self.session:
            await self.close(code=4404)
            return

        await self.accept()
        await self.send_json({"type": "status", "message": "connecting"})
        await self.start_bridge()

    async def disconnect(self, code):
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        if self._bridge_writer and not self._bridge_writer.is_closing():
            self._bridge_writer.close()
            try:
                await asyncio.wait_for(self._bridge_writer.wait_closed(), timeout=3)
            except (asyncio.TimeoutError, Exception):
                pass
        if self.session:
            await self.mark_idle()

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            msg = json.loads(text_data)
        except Exception:
            return
        t = msg.get("type")
        if t == "data":
            if self._bridge_writer and not self._bridge_writer.is_closing():
                frame = json.dumps({"t": "d", "d": msg.get("d", "")}) + "\n"
                self._bridge_writer.write(frame.encode())
                await self._bridge_writer.drain()
        elif t == "resize":
            cols = max(10, int(msg.get("cols", 80)))
            rows = max(5, int(msg.get("rows", 24)))
            if self._bridge_writer and not self._bridge_writer.is_closing():
                frame = json.dumps({"t": "r", "c": cols, "r": rows}) + "\n"
                self._bridge_writer.write(frame.encode())
                await self._bridge_writer.drain()
            await self.save_size(cols, rows)
        elif t == "ping":
            await self.send_json({"type": "pong"})

    async def start_bridge(self):
        bridge_sock = getattr(settings, "TERMINAL_BRIDGE_SOCKET", "/var/opt/piwebdev/terminal-bridge.sock")
        try:
            self._bridge_reader, self._bridge_writer = await asyncio.open_unix_connection(bridge_sock)
        except Exception as e:
            await self.send_json({"type": "error", "message": f"terminal-bridge unavailable: {e}"})
            await self.close()
            return

        init = json.dumps({"cols": self.session.last_cols, "rows": self.session.last_rows, "cwd": "/home/user01", "session_id": self.session.pk}) + "\n"
        self._bridge_writer.write(init.encode())
        await self._bridge_writer.drain()

        await self.mark_running()
        await self.send_json({"type": "status", "message": "connected"})
        self._read_task = asyncio.create_task(self.read_bridge())

    async def read_bridge(self):
        try:
            while self._bridge_reader and not self._bridge_reader.at_eof():
                line = await self._bridge_reader.readline()
                if not line:
                    break
                try:
                    frame = json.loads(line.decode())
                except Exception:
                    continue
                t = frame.get("t")
                if t == "d":
                    await self.send_json({"type": "data", "d": frame["d"]})
                elif t == "status":
                    await self.send_json({"type": "status", "message": frame.get("msg", "")})
                elif t == "err":
                    await self.send_json({"type": "error", "message": frame.get("msg", "bridge error")})
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            await self.send_json({"type": "status", "message": "disconnected"})
            await self.close()

    async def send_json(self, data):
        try:
            await self.send(text_data=json.dumps(data))
        except Exception:
            pass

    @database_sync_to_async
    def check_access(self):
        cfg, _ = UserPiSettings.objects.get_or_create(user=self.user)
        return cfg.terminal_access

    @database_sync_to_async
    def get_session(self):
        try:
            return TerminalSession.objects.get(pk=self.terminal_id, user=self.user)
        except TerminalSession.DoesNotExist:
            return None

    @database_sync_to_async
    def mark_running(self):
        self.session.status = "running"
        self.session.last_connected_at = timezone.now()
        self.session.save(update_fields=["status", "last_connected_at"])

    @database_sync_to_async
    def mark_idle(self):
        self.session.status = "idle"
        self.session.save(update_fields=["status"])

    @database_sync_to_async
    def save_size(self, cols, rows):
        self.session.last_cols = cols
        self.session.last_rows = rows
        self.session.save(update_fields=["last_cols", "last_rows"])
