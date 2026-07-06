"""GitHub deployer — initialises a git repo in the output folder and pushes to GitHub."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
from .base import run_cmd, DeployError, LogCallback


def push(
    code_path: Path,
    token: str,
    username: str,
    repo_url: str,
    branch: str = "main",
    commit_message: str = "Initial commit from SDLC Pipeline",
    log_cb: Optional[LogCallback] = None,
) -> str:
    log = log_cb or print

    if not token:
        raise DeployError("GitHub Personal Access Token is required. Set it in Settings → Credentials → GitHub.")
    if not repo_url:
        raise DeployError("GitHub repo URL is required (e.g. https://github.com/username/my-app).")

    # Inject token into remote URL: https://token@github.com/user/repo.git
    auth_url = re.sub(r"^https://", f"https://{token}@", repo_url.rstrip("/"))
    if not auth_url.endswith(".git"):
        auth_url += ".git"

    log(f"🐙 Pushing generated code to GitHub → {repo_url}")

    git_config = [
        ("user.email", f"{username}@users.noreply.github.com"),
        ("user.name", username or "SDLC Pipeline"),
    ]

    # ── 1. Init repo ───────────────────────────────────────────────────────────
    git_dir = code_path / ".git"
    if not git_dir.exists():
        log("📁 Initialising git repository...")
        run_cmd(["git", "init", "-b", branch], cwd=code_path, log_cb=log_cb)
    else:
        log("📁 Git repository already initialised.")

    # ── 2. Configure user ──────────────────────────────────────────────────────
    for key, val in git_config:
        run_cmd(["git", "config", key, val], cwd=code_path, log_cb=log_cb)

    # ── 3. Create .gitignore if missing ────────────────────────────────────────
    gitignore = code_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "__pycache__/\n*.pyc\n.env\n*.credentials.json\n.credentials.json\n"
            "node_modules/\n.DS_Store\n*.egg-info/\ndist/\nbuild/\n.terraform/\n"
        )
        log("📝 Created .gitignore")

    # ── 4. Stage all files ─────────────────────────────────────────────────────
    log("📦 Staging all files...")
    run_cmd(["git", "add", "."], cwd=code_path, log_cb=log_cb)

    # ── 5. Commit ──────────────────────────────────────────────────────────────
    log(f"💾 Committing: '{commit_message}'")
    try:
        run_cmd(["git", "commit", "-m", commit_message], cwd=code_path, log_cb=log_cb)
    except Exception:
        log("   (nothing to commit or already committed — continuing)")

    # ── 6. Set remote ─────────────────────────────────────────────────────────
    log("🔗 Setting remote origin...")
    try:
        run_cmd(["git", "remote", "add", "origin", auth_url], cwd=code_path, log_cb=log_cb)
    except Exception:
        run_cmd(["git", "remote", "set-url", "origin", auth_url], cwd=code_path, log_cb=log_cb)

    # ── 7. Push ───────────────────────────────────────────────────────────────
    log(f"⬆️  Pushing to {repo_url} (branch: {branch})...")
    run_cmd(["git", "push", "-u", "origin", branch, "--force"], cwd=code_path, log_cb=log_cb)

    log(f"✅ Code pushed to GitHub! → {repo_url}")
    return repo_url
