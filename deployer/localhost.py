"""Localhost deployer — runs docker-compose up in the generated code folder."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from .base import run_cmd, DeployError, LogCallback


def deploy(code_path: Path, log_cb: Optional[LogCallback] = None) -> str:
    """
    Start the application locally with Docker Compose.
    Returns the local URL on success.
    """
    log = log_cb or print

    # Find docker-compose file
    compose_file = None
    for name in ("docker-compose.yml", "docker-compose.yaml"):
        candidate = code_path / name
        if candidate.exists():
            compose_file = candidate
            break

    if not compose_file:
        # Check in deployments subdir
        for name in ("docker-compose.yml", "docker-compose.yaml"):
            candidate = code_path / "deployments" / name
            if candidate.exists():
                compose_file = candidate
                code_path = code_path / "deployments"
                break

    if not compose_file:
        raise DeployError(
            "No docker-compose.yml found. "
            "Make sure the pipeline has completed and generated deployment files."
        )

    log(f"📂 Using compose file: {compose_file}")

    # Pull latest images
    log("⬇  Pulling Docker images...")
    run_cmd(["docker", "compose", "pull", "--ignore-pull-failures"], cwd=code_path, log_cb=log_cb)

    # Build and start
    log("🏗️  Building and starting services...")
    run_cmd(["docker", "compose", "up", "--build", "-d"], cwd=code_path, log_cb=log_cb)

    # Show running containers
    log("📋 Running containers:")
    run_cmd(["docker", "compose", "ps"], cwd=code_path, log_cb=log_cb)

    log("✅ Application started!")
    log("🌐 API: http://localhost:8000")
    log("📖 Docs: http://localhost:8000/docs")
    log("🗄️  pgAdmin: http://localhost:5050 (if included)")

    return "http://localhost:8000"


def stop(code_path: Path, log_cb: Optional[LogCallback] = None) -> None:
    run_cmd(["docker", "compose", "down"], cwd=code_path, log_cb=log_cb)


def get_logs(code_path: Path, service: str = "", log_cb: Optional[LogCallback] = None) -> None:
    cmd = ["docker", "compose", "logs", "--tail=100"]
    if service:
        cmd.append(service)
    run_cmd(cmd, cwd=code_path, log_cb=log_cb)
