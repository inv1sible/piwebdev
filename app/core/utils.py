import os
import re
import zipfile
from pathlib import Path
from django.conf import settings
from django.utils.text import slugify


def project_slug(name: str) -> str:
    slug = slugify(name) or re.sub(r"[^a-zA-Z0-9_.-]+", "-", name.strip()).strip("-")
    return slug[:100]


def resolve_project_path(project, rel="") -> Path:
    root = Path(project.path).resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path escapes project root")
    return target


def safe_workspace_path(slug: str) -> Path:
    target = (settings.PROJECTS_ROOT / slug).resolve()
    if target != settings.PROJECTS_ROOT and settings.PROJECTS_ROOT not in target.parents:
        raise ValueError("Path escapes workspace")
    return target


def safe_extract_zip(zip_file, destination: Path):
    destination = destination.resolve()
    with zipfile.ZipFile(zip_file) as zf:
        for info in zf.infolist():
            target = (destination / info.filename).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError(f"Unsafe zip entry: {info.filename}")
        zf.extractall(destination)


def list_dir(path: Path):
    items = []
    for p in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if p.name in {".git", ".pi-sessions", "node_modules", "__pycache__"}:
            continue
        items.append({"name": p.name, "path": str(p), "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else None})
    return items
