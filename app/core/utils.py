import json
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


def get_pi_models_config():
    """Read pi agent models.json configuration.
    
    Returns:
        dict: Parsed models configuration with provider and model info,
              or empty dict if file not found/invalid.
    """
    # Try multiple possible locations for models.json
    possible_paths = [
        Path.home() / '.pi' / 'agent' / 'models.json',
        Path('/home/entwickler/.pi/agent/models.json'),
    ]
    
    # Also check env variable for custom path
    custom_path = os.environ.get('PI_MODELS_JSON_PATH')
    if custom_path:
        possible_paths.insert(0, Path(custom_path))
    
    for path in possible_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
    
    return {}


def get_provider_choices():
    """Generate provider choices from models.json or fallback to defaults.
    
    Returns:
        list of tuples: (value, label) for provider dropdown.
    """
    config = get_pi_models_config()
    choices = [("", "— select provider —")]
    
    # Add providers from models.json
    providers = config.get('providers', {})
    for provider_id, provider_config in providers.items():
        # Use id as name if not specified
        name = provider_config.get('name', provider_id.title())
        choices.append((provider_id, f"{name} ({provider_id})"))
    
    # Add default providers if no custom config
    if not providers:
        choices = [
            ("", "— select provider —"),
            ("anthropic", "Anthropic"),
            ("openai", "OpenAI"),
            ("openai-codex", "OpenAI Codex"),
            ("gemini", "Gemini"),
            ("bedrock", "AWS Bedrock"),
            ("vertex", "Google Vertex"),
            ("ollama", "Ollama (local)"),
        ]
    
    return choices


def get_model_choices():
    """Generate model choices from models.json or fallback to defaults.
    
    Returns:
        list of tuples: (value, label) for model dropdown.
    """
    config = get_pi_models_config()
    choices = [("", "— select model —")]
    
    # Add models from models.json
    providers = config.get('providers', {})
    has_custom = False
    
    for provider_id, provider_config in providers.items():
        models = provider_config.get('models', [])
        if models:
            has_custom = True
            
            for model in models:
                model_id = model.get('id', '')
                model_name = model.get('name', model_id)
                # Add reasoning indicator
                reasoning = " [R]" if model.get('reasoning') else ""
                choices.append((model_id, f"{model_name}{reasoning}"))
    
    # Add fallback models if no custom config
    if not has_custom:
        choices = [
            ("", "— select model —"),
            # Anthropic
            ("claude-opus-4-7", "Claude Opus 4.7"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
            ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet"),
            ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
            # OpenAI
            ("gpt-5.5", "GPT-5.5"),
            ("gpt-4o", "GPT-4o"),
            ("gpt-4o-mini", "GPT-4o Mini"),
            ("o3", "o3"),
            ("o4-mini", "o4-mini"),
            ("codex-mini-latest", "Codex Mini"),
            # Gemini
            ("gemini-2.5-pro", "Gemini 2.5 Pro"),
            ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ]
    
    return choices
