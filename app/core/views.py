import json
import os
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.contrib.auth.views import LoginView
from django_ratelimit.decorators import ratelimit
from .auth_forms import UsernameOrEmailAuthenticationForm
from .forms import ProjectCreateForm, ProjectRenameForm, ProjectMemoryForm, ProjectPiSettingsForm, UserPiSettingsForm
from .models import Project, ProjectMemory, ProjectPiSettings, UserPiSettings, PiSession, ChatMessage, TerminalSession
from .utils import project_slug, safe_workspace_path, resolve_project_path, list_dir, safe_extract_zip, get_provider_choices, get_model_choices, get_pi_models_config


def run_git(cwd, args, timeout=30):
    p = subprocess.run(["git", "-c", "safe.directory=*", *args], cwd=cwd, text=True, capture_output=True, timeout=timeout)
    return {"ok": p.returncode == 0, "stdout": p.stdout, "stderr": p.stderr, "code": p.returncode}


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="dispatch")
class PiLoginView(LoginView):
    template_name = "core/login.html"
    authentication_form = UsernameOrEmailAuthenticationForm


def sync_projects_from_disk(user):
    root = settings.PROJECTS_ROOT
    if not root.exists():
        return 0
    count = 0
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        slug = project_slug(path.name)
        project, created = Project.objects.get_or_create(
            path=str(path.resolve()),
            defaults={"name": path.name, "slug": slug, "created_by": user},
        )
        if created:
            ProjectMemory.objects.get_or_create(project=project)
            ProjectPiSettings.objects.get_or_create(project=project)
            count += 1
    return count


@login_required
def dashboard(request):
    sync_projects_from_disk(request.user)
    projects = Project.objects.all()
    return render(request, "core/dashboard.html", {"projects": projects})


@login_required
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def project_create(request):
    form = ProjectCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        slug = project_slug(form.cleaned_data["name"])
        path = safe_workspace_path(slug)
        if path.exists() or Project.objects.filter(slug=slug).exists():
            messages.error(request, "Project already exists.")
        else:
            path.mkdir(parents=False)
            if form.cleaned_data["add_readme"]:
                (path / "README.md").write_text(f"# {form.cleaned_data['name']}\n")
            if form.cleaned_data["init_git"]:
                run_git(path, ["init"])
            project = Project.objects.create(name=form.cleaned_data["name"], slug=slug, path=str(path), created_by=request.user)
            ProjectMemory.objects.create(project=project)
            ProjectPiSettings.objects.create(project=project)
            return redirect("project_detail", pk=project.pk)
    return render(request, "core/project_form.html", {"form": form, "title": "Create project"})


def _group_into_tasks(msgs):
    tasks, current_task = [], None
    for msg in msgs:
        if msg.role == "user":
            current_task = {"prompt": msg, "tools": [], "result": None, "manual_done": bool(msg.metadata.get("manual_done"))}
            tasks.append(current_task)
        elif msg.role == "assistant" and msg.metadata.get("final"):
            if current_task:
                current_task["result"] = msg
        elif current_task is not None:
            current_task["tools"].append(msg)
        else:
            current_task = {"prompt": None, "tools": [msg], "result": None, "manual_done": False}
            tasks.append(current_task)
    return tasks


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    session = project.sessions.filter(user=request.user, status__in=["idle", "running", "stopped"]).first()
    if not session:
        session = PiSession.objects.create(project=project, user=request.user, title="Main session")
    ProjectMemory.objects.get_or_create(project=project)
    ProjectPiSettings.objects.get_or_create(project=project)
    sections, current_msgs = [], []
    for msg in session.messages.order_by("created_at"):
        if msg.role == "system" and msg.metadata.get("type") == "checkpoint":
            sections.append({"checkpoint": msg, "tasks": _group_into_tasks(current_msgs)})
            current_msgs = []
        else:
            current_msgs.append(msg)
    sections.append({"checkpoint": None, "tasks": _group_into_tasks(current_msgs)})
    return render(request, "core/project_detail.html", {"project": project, "session": session, "sections": sections})


@login_required
def project_rename(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = ProjectRenameForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("project_detail", pk=project.pk)
    return render(request, "core/project_form.html", {"form": form, "title": "Rename project"})


@login_required
def project_memory(request, pk):
    project = get_object_or_404(Project, pk=pk)
    memory_file = Path(project.path) / "MEMORY.md"
    default = "# General Memory\n\n\n# Todos\n\n\n# Ideas For Later\n"
    if request.method == "POST":
        content = request.POST.get("content", default)
        memory_file.write_text(content, encoding="utf-8")
        messages.success(request, "Memory saved.")
        return redirect("project_detail", pk=project.pk)
    content = memory_file.read_text(encoding="utf-8") if memory_file.exists() else default
    return render(request, "core/project_memory.html", {
        "project": project,
        "content": content,
    })


@login_required
def api_memory(request, pk):
    project = get_object_or_404(Project, pk=pk)
    memory_file = Path(project.path) / "MEMORY.md"
    default = "# General Memory\n\n\n# Todos\n\n\n# Ideas For Later\n"
    if request.method == "POST":
        data = json.loads(request.body)
        memory_file.write_text(data.get("content", default), encoding="utf-8")
        return JsonResponse({"ok": True})
    content = memory_file.read_text(encoding="utf-8") if memory_file.exists() else default
    return JsonResponse({"content": content})


@login_required
def api_agents_md(request, pk):
    project = get_object_or_404(Project, pk=pk)
    agents_file = Path(project.path) / "AGENTS.md"
    if request.method == "POST":
        data = json.loads(request.body)
        agents_file.write_text(data.get("content", ""), encoding="utf-8")
        return JsonResponse({"ok": True})
    content = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""
    return JsonResponse({"content": content})


_CONTEXT_FILES = {"AGENTS.md", "CLAUDE.md"}


def _pi_agent_dir():
    auth_path = os.environ.get("PI_AUTH_JSON", "")
    return Path(auth_path).parent if auth_path else (Path.home() / ".pi" / "agent")


@login_required
def api_project_context(request, pk):
    """Read/write AGENTS.md or CLAUDE.md in the project root."""
    project = get_object_or_404(Project, pk=pk)
    if request.method == "POST":
        data = json.loads(request.body)
        fname = data.get("file", "")
        if fname not in _CONTEXT_FILES:
            return JsonResponse({"error": "file must be AGENTS.md or CLAUDE.md"}, status=400)
        (Path(project.path) / fname).write_text(data.get("content", ""), encoding="utf-8")
        return JsonResponse({"ok": True})
    fname = request.GET.get("file", "")
    if fname not in _CONTEXT_FILES:
        return JsonResponse({"error": "file must be AGENTS.md or CLAUDE.md"}, status=400)
    path = Path(project.path) / fname
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return JsonResponse({"content": content, "path": str(path)})


@login_required
def api_global_context(request):
    """Read/write global AGENTS.md or CLAUDE.md in ~/.pi/agent/."""
    if request.method == "POST":
        data = json.loads(request.body)
        fname = data.get("file", "")
    else:
        fname = request.GET.get("file", "")
    if fname not in _CONTEXT_FILES:
        return JsonResponse({"error": "file must be AGENTS.md or CLAUDE.md"}, status=400)
    path = _pi_agent_dir() / fname
    if request.method == "POST":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data.get("content", ""), encoding="utf-8")
        return JsonResponse({"ok": True})
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return JsonResponse({"content": content, "path": str(path)})


@login_required
def api_models(request):
    config = get_pi_models_config()
    by_provider = {
        pid: [m["id"] for m in pcfg.get("models", [])]
        for pid, pcfg in config.get("providers", {}).items()
    }
    model_reasoning = {
        m["id"]: bool(m.get("reasoning"))
        for pcfg in config.get("providers", {}).values()
        for m in pcfg.get("models", [])
        if m.get("id")
    }
    return JsonResponse({
        "providers": get_provider_choices(),
        "models": get_model_choices(),
        "by_provider": by_provider,
        "model_reasoning": model_reasoning,
    })


@login_required
def api_user_prefs(request):
    cfg, _ = UserPiSettings.objects.get_or_create(user=request.user)
    if request.method == "POST":
        data = json.loads(request.body)
        for field in ["provider", "model", "thinking_level", "extra_args"]:
            if field in data:
                setattr(cfg, field, data[field])
        if "use_context_files" in data:
            cfg.use_context_files = bool(data["use_context_files"])
        cfg.save()
        return JsonResponse({"ok": True})
    return JsonResponse({
        "provider": cfg.provider or "",
        "model": cfg.model or "",
        "thinking_level": cfg.thinking_level or "",
        "extra_args": cfg.extra_args or "",
        "use_context_files": cfg.use_context_files,
    })


@login_required
def api_models_edit(request):
    auth_path = os.environ.get("PI_AUTH_JSON", "")
    pi_agent_dir = Path(auth_path).parent if auth_path else (Path.home() / ".pi" / "agent")

    # Build read-only pi catalog: merge builtin + pi's own models.json
    pi_catalog: dict = {"providers": {}}
    from .utils import _merge_providers
    builtin_path = pi_agent_dir / "builtin-models.json"
    if builtin_path.exists():
        try:
            _merge_providers(pi_catalog, json.loads(builtin_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    pi_models_path = pi_agent_dir / "models.json"
    if pi_models_path.exists():
        try:
            _merge_providers(pi_catalog, json.loads(pi_models_path.read_text(encoding="utf-8")))
        except Exception:
            pass

    path_str = os.environ.get("PI_MODELS_JSON_PATH", "")
    if not path_str:
        return JsonResponse({
            "error": "PI_MODELS_JSON_PATH is not set. Add it to .env to enable the provider catalog editor.",
            "pi_catalog": pi_catalog,
            "pi_catalog_path": str(pi_models_path),
        }, status=400)
    path = Path(path_str)
    if request.method == "POST":
        data = json.loads(request.body)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data.get("config", {}), indent=2), encoding="utf-8")
        return JsonResponse({"ok": True})
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"providers": {}}
    return JsonResponse({
        "config": config,
        "path": str(path),
        "pi_catalog": pi_catalog,
        "pi_catalog_path": str(pi_models_path),
    })


_KNOWN_PROVIDERS = [
    {"id": "google",       "name": "Google Gemini",   "env": "GEMINI_API_KEY"},
    {"id": "anthropic",    "name": "Anthropic Claude", "env": "ANTHROPIC_API_KEY"},
    {"id": "openai",       "name": "OpenAI",           "env": "OPENAI_API_KEY"},
    {"id": "openai-codex", "name": "OpenAI Codex",     "env": None, "oauth_only": True},
    {"id": "xai",          "name": "xAI Grok",         "env": "XAI_API_KEY"},
    {"id": "deepseek",     "name": "DeepSeek",         "env": "DEEPSEEK_API_KEY"},
    {"id": "groq",         "name": "Groq",             "env": "GROQ_API_KEY"},
    {"id": "mistral",      "name": "Mistral",          "env": "MISTRAL_API_KEY"},
    {"id": "openrouter",   "name": "OpenRouter",       "env": "OPENROUTER_API_KEY"},
    {"id": "fireworks",    "name": "Fireworks",        "env": "FIREWORKS_API_KEY"},
    {"id": "ollama",       "name": "Ollama (local)",   "env": None, "no_key": True},
]


def _auth_path():
    return Path(os.environ.get("PI_AUTH_JSON", "/home/user01/.pi/agent/auth.json"))


def _read_auth():
    p = _auth_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _write_auth(data):
    p = _auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


@login_required
def auth_page(request):
    return redirect("/settings/#keys")


@login_required
def api_auth(request):
    auth_data = _read_auth()
    if request.method == "POST":
        body = json.loads(request.body)
        provider = body.get("provider", "").strip()
        key = body.get("key", "").strip()
        action = body.get("action", "set")
        if not provider:
            return JsonResponse({"error": "provider required"}, status=400)
        if action == "delete":
            auth_data.pop(provider, None)
        else:
            if not key:
                return JsonResponse({"error": "key required"}, status=400)
            auth_data[provider] = {"type": "api_key", "key": key}
        try:
            _write_auth(auth_data)
        except OSError as e:
            return JsonResponse({"error": f"Cannot write auth.json: {e}"}, status=500)
        return JsonResponse({"ok": True})

    result = []
    for prov in _KNOWN_PROVIDERS:
        pid = prov["id"]
        cred = auth_data.get(pid)
        status, key_preview, cred_type = "not_set", None, None
        if cred:
            cred_type = cred.get("type")
            if cred_type == "api_key":
                k = cred.get("key", "")
                status = "set"
                key_preview = (k[:4] + "…" + k[-4:]) if len(k) > 10 else "•••"
            elif cred_type == "oauth":
                status = "oauth"
        result.append({
            "id": pid, "name": prov["name"], "env": prov.get("env"),
            "oauth_only": prov.get("oauth_only", False),
            "no_key": prov.get("no_key", False),
            "status": status, "key_preview": key_preview,
        })
    # Also include any unknown providers already in auth.json
    known_ids = {p["id"] for p in _KNOWN_PROVIDERS}
    for pid, cred in auth_data.items():
        if pid not in known_ids:
            cred_type = cred.get("type")
            k = cred.get("key", "") if cred_type == "api_key" else ""
            result.append({
                "id": pid, "name": pid, "env": None, "oauth_only": cred_type == "oauth",
                "no_key": False, "status": "oauth" if cred_type == "oauth" else "set",
                "key_preview": (k[:4] + "…" + k[-4:]) if len(k) > 10 else ("•••" if k else None),
            })
    return JsonResponse({"providers": result})


@login_required
def api_ollama_tags(request):
    url = request.GET.get("url", "").strip().rstrip("/")
    if not url:
        return JsonResponse({"error": "url parameter required"}, status=400)
    try:
        req = urllib.request.Request(url + "/api/tags", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=502)


@login_required
def providers_page(request):
    return redirect("/settings/#providers")


@login_required
def user_settings(request):
    return render(request, "core/settings.html")


@login_required
def project_settings(request, pk):
    project = get_object_or_404(Project, pk=pk)
    obj, _ = ProjectPiSettings.objects.get_or_create(project=project)
    user_cfg, _ = UserPiSettings.objects.get_or_create(user=request.user)
    form = ProjectPiSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("project_detail", pk=project.pk)
    # Pre-select the effective value for dropdown fields when project field is empty
    fallbacks = {
        "provider": user_cfg.provider or settings.DEFAULT_PI_PROVIDER,
        "model": user_cfg.model or settings.DEFAULT_PI_MODEL,
        "thinking_level": user_cfg.thinking_level or settings.DEFAULT_PI_THINKING,
    }
    for field, fallback in fallbacks.items():
        if not getattr(obj, field) and fallback:
            form.initial[field] = fallback
    if user_cfg.extra_args and not obj.extra_args:
        form.fields["extra_args"].widget.attrs["placeholder"] = f"default: {user_cfg.extra_args}"
    catalog = get_pi_models_config()
    return render(request, "core/project_settings.html", {
        "form": form,
        "project": project,
        "catalog_json": json.dumps(catalog.get("providers", {})),
        "effective": fallbacks,
    })


@login_required
@require_POST
def session_clear(request, pk):
    import socket as _sock
    session = get_object_or_404(PiSession, pk=pk, user=request.user)
    session.messages.all().delete()
    # Kill the running pi process before wiping the session files
    if session.session_dir:
        sdir = Path(session.session_dir)
        bridge_sock = getattr(settings, "PI_BRIDGE_SOCKET", "/var/opt/piwebdev/pi-bridge.sock")
        try:
            s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
            s.settimeout(3)
            s.connect(bridge_sock)
            s.sendall((json.dumps({"type": "kill", "session_key": str(sdir)}) + "\n").encode())
            s.recv(256)
            s.close()
        except Exception:
            pass
        # Remove pi JSONL files so next start is fully fresh
        if sdir.exists() and sdir.is_dir():
            try:
                shutil.rmtree(sdir)
            except Exception:
                pass
        session.session_dir = ""
        session.save(update_fields=["session_dir", "updated_at"])
    messages.success(request, "Session cleared.")
    return redirect("project_detail", pk=session.project_id)


@login_required
@require_POST
def task_delete(request, pk):
    get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    prompt_msg = get_object_or_404(
        ChatMessage,
        pk=data.get("message_id"),
        role="user",
        session__project_id=pk,
        session__user=request.user,
    )
    session = prompt_msg.session
    next_user = session.messages.filter(
        role="user",
        created_at__gt=prompt_msg.created_at,
    ).order_by("created_at").first()
    qs = session.messages.filter(created_at__gte=prompt_msg.created_at)
    if next_user:
        qs = qs.filter(created_at__lt=next_user.created_at)
    qs.delete()
    return JsonResponse({"ok": True})


@login_required
def file_tree(request, pk):
    project = get_object_or_404(Project, pk=pk)
    rel = request.GET.get("path", "")
    try:
        path = resolve_project_path(project, rel)
        return JsonResponse({"items": list_dir(path), "rel": rel})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def file_read(request, pk):
    project = get_object_or_404(Project, pk=pk)
    try:
        path = resolve_project_path(project, request.GET.get("path", ""))
        if not path.is_file():
            return JsonResponse({"error": "not a file"}, status=400)
        return JsonResponse({"content": path.read_text(errors="replace"), "path": request.GET.get("path", "")})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def file_save(request, pk):
    project = get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    try:
        path = resolve_project_path(project, data.get("path", ""))
        path.write_text(data.get("content", ""))
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def file_rename(request, pk):
    project = get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    old = data.get("path", "")
    new_name = Path(data.get("new_name", "")).name
    if not new_name:
        return JsonResponse({"error": "new name required"}, status=400)
    try:
        src = resolve_project_path(project, old)
        dst = resolve_project_path(project, str(Path(old).parent / new_name))
        if dst.exists():
            return JsonResponse({"error": "target already exists"}, status=409)
        src.rename(dst)
        return JsonResponse({"ok": True, "path": str(Path(old).parent / new_name).lstrip(".")})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def task_mark_done(request, pk):
    get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    msg = get_object_or_404(
        ChatMessage,
        pk=data.get("message_id"),
        role="user",
        session__project_id=pk,
        session__user=request.user,
    )
    meta = dict(msg.metadata or {})
    meta["manual_done"] = True
    meta["manual_done_at"] = timezone.now().isoformat()
    msg.metadata = meta
    msg.save(update_fields=["metadata"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def file_upload(request, pk):
    project = get_object_or_404(Project, pk=pk)
    rel = request.POST.get("path", "")
    try:
        dest = resolve_project_path(project, rel)
        dest.mkdir(parents=True, exist_ok=True)
        for f in request.FILES.getlist("files"):
            if f.name.lower().endswith(".zip") and request.POST.get("extract_zip") == "1":
                safe_extract_zip(f, dest)
            else:
                out = resolve_project_path(project, str(Path(rel) / Path(f.name).name))
                with out.open("wb") as w:
                    for chunk in f.chunks():
                        w.write(chunk)
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def file_new(request, pk):
    project = get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    try:
        path = resolve_project_path(project, data.get("path", ""))
        if path.exists():
            return JsonResponse({"error": "already exists"}, status=409)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def file_delete(request, pk):
    project = get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    try:
        path = resolve_project_path(project, data.get("path", ""))
        root = Path(project.path).resolve()
        if path == root:
            return JsonResponse({"error": "cannot delete project root"}, status=400)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def git_diff(request, pk):
    project = get_object_or_404(Project, pk=pk)
    status = run_git(project.path, ["status", "--short"])
    if not status["ok"]:
        err = (status["stderr"] or status["stdout"]).split("\n")[0].strip() or "git status failed"
        return JsonResponse({"error": err}, status=500)
    diff = run_git(project.path, ["diff", "--no-ext-diff"], timeout=60)
    # exit code 1 means there are differences (normal); >= 2 is an actual error
    if diff["code"] >= 2:
        err = (diff["stderr"] or diff["stdout"]).split("\n")[0].strip() or "git diff failed"
        return JsonResponse({"error": err}, status=500)
    return JsonResponse({"status": status["stdout"], "diff": diff["stdout"]})


@login_required
@require_POST
def git_commit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    data = json.loads(request.body or b"{}")
    message = (data.get("message") or "Update project").strip()
    add = run_git(project.path, ["add", "-A"])
    if not add["ok"]:
        return JsonResponse({"error": add["stderr"] or add["stdout"]}, status=500)
    commit = run_git(project.path, ["commit", "-m", message])
    if not commit["ok"]:
        return JsonResponse({"error": commit["stderr"] or commit["stdout"]}, status=500)
    return JsonResponse({"ok": True, "output": commit["stdout"] or commit["stderr"]})


@login_required
@require_POST
def git_push(request, pk):
    project = get_object_or_404(Project, pk=pk)
    push = run_git(project.path, ["push"], timeout=120)
    if not push["ok"]:
        return JsonResponse({"error": push["stderr"] or push["stdout"]}, status=500)
    return JsonResponse({"ok": True, "output": push["stdout"] or push["stderr"]})


@login_required
@require_POST
def git_init(request, pk):
    project = get_object_or_404(Project, pk=pk)
    result = run_git(project.path, ["init"])
    if not result["ok"]:
        return JsonResponse({"error": result["stderr"] or result["stdout"]}, status=500)
    return JsonResponse({"ok": True, "output": result["stdout"] or result["stderr"]})


@login_required
def terminal_page(request):
    cfg, _ = UserPiSettings.objects.get_or_create(user=request.user)
    if not cfg.terminal_access:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Terminal access not granted. Enable it in Django admin → User Pi Settings.")
    session, _ = TerminalSession.objects.get_or_create(user=request.user)
    return render(request, "core/terminal.html", {"session": session})


def manifest(request):
    return JsonResponse({
        "id": "/",
        "name": "π webui",
        "short_name": "π webui",
        "description": "Installable Pi coding agent web workspace",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone", "browser"],
        "orientation": "any",
        "background_color": "#0b0f14",
        "theme_color": "#72f1b8",
        "categories": ["developer", "productivity"],
        "icons": [
            {"src": "/static/core/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
        ],
        "shortcuts": [
            {"name": "Projects", "short_name": "Projects", "url": "/", "icons": [{"src": "/static/core/icon.svg", "sizes": "any", "type": "image/svg+xml"}]},
        ],
    })


def offline(request):
    return render(request, "core/offline.html")


def service_worker(request):
    version = "20260508-19"
    body = f"""
const CACHE = 'piwebdev-{version}';
const ASSETS = [
  '/',
  '/offline/',
  '/manifest.json',
  '/static/core/style.css?v={version}',
  '/static/core/app.js?v={version}',
  '/static/core/icon.svg'
];
self.addEventListener('install', event => {{
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
}});
self.addEventListener('activate', event => {{
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
}});
self.addEventListener('message', event => {{
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
}});
self.addEventListener('fetch', event => {{
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== location.origin || url.pathname.startsWith('/ws/') || url.pathname.startsWith('/api/')) return;
  if (req.mode === 'navigate') {{
    event.respondWith(fetch(req).catch(() => caches.match('/offline/')));
    return;
  }}
  if (req.method === 'GET') {{
    event.respondWith(caches.match(req).then(cached => cached || fetch(req).then(res => {{
      const copy = res.clone(); caches.open(CACHE).then(cache => cache.put(req, copy)); return res;
    }})));
  }}
}});
""".strip() + "\n"
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
