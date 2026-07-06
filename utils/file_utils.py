"""
Shared file I/O helpers used across multiple agents.
"""

import re
import json
import shutil
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime
from typing import Any
from loguru import logger
from config.settings import settings

# ── Project-scoped output context ─────────────────────────────────────────────
# Set once per pipeline run (in orchestrator/pipeline.py) before agents execute.
# Thread-safe via Python contextvars — each thread inherits the value set by its
# parent, so agents running in the same async pipeline thread share the same project.

_current_project: ContextVar[str] = ContextVar("current_project", default="")


def set_current_project(project_name: str) -> None:
    """Call this before starting a pipeline run to scope all output files."""
    safe = _safe_name(project_name)
    _current_project.set(safe)
    logger.info(f"Output project set to: '{safe}'")


def get_current_project() -> str:
    return _current_project.get()


def _safe_name(name: str) -> str:
    """Convert any project name to a safe directory name."""
    safe = re.sub(r"[^\w\- ]", "", name).strip().replace(" ", "_").lower()
    return safe or "project"


def outputs_path(subdir: str, filename: str) -> Path:
    """Return an absolute path inside outputs/{project}/{subdir}/, creating it if needed."""
    project = _current_project.get()
    if project:
        base = Path(settings.outputs_dir) / project / subdir
    else:
        base = Path(settings.outputs_dir) / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base / filename


def project_outputs_root() -> Path:
    """Return the root folder for the current project's outputs."""
    project = _current_project.get()
    root = Path(settings.outputs_dir) / project if project else Path(settings.outputs_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_json(data: Any, subdir: str, filename: str) -> Path:
    path = outputs_path(subdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Saved JSON → {path}")
    return path


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_text(content: str, subdir: str, filename: str) -> Path:
    path = outputs_path(subdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Saved text → {path}")
    return path


def timestamped_name(prefix: str, ext: str) -> str:
    """Generate a filename like  requirements_20260702_143500.json"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{ext}"


def get_file_extension(filepath: str) -> str:
    return Path(filepath).suffix.lower()


def copy_to_outputs(src: str | Path, subdir: str) -> Path:
    src = Path(src)
    dest = outputs_path(subdir, src.name)
    shutil.copy2(src, dest)
    logger.info(f"Copied {src} → {dest}")
    return dest
