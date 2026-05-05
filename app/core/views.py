import json
import os
import shlex
import shutil
import subprocess
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
from .forms import ProjectCreateForm, ProjectRenameForm, ProjectMemoryForm, ProjectPiSettingsForm
from .models import Project, ProjectMemory, ProjectPiSettings, UserPiSettings, PiSession, ChatMessage
from .utils import project_slug, safe_workspace_path, resolve_project_path, list_dir, safe_extract_zip


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


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    session = project.sessions.filter(user=request.user, status__in=["idle", "running", "stopped"]).first()
    if not session:
        session = PiSession.objects.create(project=project, user=request.user, title="Main session")
    ProjectMemory.objects.get_or_create(project=project)
    ProjectPiSettings.objects.get_or_create(project=project)
    tasks = []
    current_task = None
    for msg in session.messages.order_by("created_at"):
        if msg.role == "user":
            current_task = {"prompt": msg, "tools": [], "result": None}
            tasks.append(current_task)
        elif msg.role == "assistant" and msg.metadata.get("final"):
            if current_task:
                current_task["result"] = msg
        elif current_task is not None:
            current_task["tools"].append(msg)
        else:
            current_task = {"prompt": None, "tools": [msg], "result": None}
            tasks.append(current_task)
    return render(request, "core/project_detail.html", {"project": project, "session": session, "tasks": tasks})


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
    return render(request, "core/project_form.html", {"form": form, "title": "Project Pi settings"})


@login_required
@require_POST
def session_clear(request, pk):
    session = get_object_or_404(PiSession, pk=pk, user=request.user)
    session.messages.all().delete()
    messages.success(request, "Session history cleared.")
    return redirect("project_detail", pk=session.project_id)


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
    version = "20260504-5"
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
