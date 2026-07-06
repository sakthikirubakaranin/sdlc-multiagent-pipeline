"""GCP deployer — authenticates with a Service Account key, builds & pushes Docker
image to Artifact Registry, then deploys to Cloud Run (or runs terraform apply)."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from .base import run_cmd, DeployError, LogCallback


def deploy(
    code_path: Path,
    project_id: str,
    region: str,
    service_account_json: str,
    artifact_registry: str = "",
    app_name: str = "sdlc-app",
    use_terraform: bool = False,
    log_cb: Optional[LogCallback] = None,
) -> str:
    log = log_cb or print

    if not project_id:
        raise DeployError("GCP project_id is required. Set it in Settings → Credentials → GCP.")
    if not service_account_json:
        raise DeployError("GCP service account JSON is required. Set it in Settings → Credentials → GCP.")

    # Write SA key to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(service_account_json)
        sa_key_path = f.name

    try:
        env = {"GOOGLE_APPLICATION_CREDENTIALS": sa_key_path}

        # ── 1. Authenticate ────────────────────────────────────────────────────
        log("🔑 Authenticating with GCP service account...")
        run_cmd(
            ["gcloud", "auth", "activate-service-account", f"--key-file={sa_key_path}"],
            log_cb=log_cb,
        )
        run_cmd(["gcloud", "config", "set", "project", project_id], log_cb=log_cb)
        run_cmd(["gcloud", "config", "set", "run/region", region], log_cb=log_cb)

        if use_terraform:
            return _terraform_deploy(code_path, project_id, region, env, app_name, log_cb)
        else:
            return _cloudrun_deploy(code_path, project_id, region, artifact_registry, app_name, sa_key_path, env, log_cb)

    finally:
        os.unlink(sa_key_path)


def _cloudrun_deploy(
    code_path: Path, project_id: str, region: str,
    artifact_registry: str, app_name: str, sa_key_path: str,
    env: dict, log_cb: Optional[LogCallback],
) -> str:
    log = log_cb or print

    registry = artifact_registry or f"{region}-docker.pkg.dev/{project_id}/{app_name}"
    image_tag = f"{registry}/{app_name}:latest"

    # ── 2. Enable required APIs ────────────────────────────────────────────────
    log("🔧 Enabling GCP APIs (run, artifactregistry, sqladmin)...")
    for api in ["run.googleapis.com", "artifactregistry.googleapis.com"]:
        run_cmd(["gcloud", "services", "enable", api, "--project", project_id], log_cb=log_cb)

    # ── 3. Create Artifact Registry repo if needed ─────────────────────────────
    log("📦 Ensuring Artifact Registry repository exists...")
    try:
        run_cmd([
            "gcloud", "artifacts", "repositories", "create", app_name,
            "--repository-format=docker", f"--location={region}", "--project", project_id,
        ], log_cb=log_cb)
    except Exception:
        log("   (repository may already exist — continuing)")

    # ── 4. Configure Docker for Artifact Registry ──────────────────────────────
    log("🐳 Configuring Docker auth for Artifact Registry...")
    run_cmd(["gcloud", "auth", "configure-docker", f"{region}-docker.pkg.dev", "--quiet"], log_cb=log_cb)

    # ── 5. Build & Push ────────────────────────────────────────────────────────
    log(f"🏗️  Building Docker image: {image_tag}")
    run_cmd(["docker", "build", "-t", image_tag, "."], cwd=code_path, log_cb=log_cb)

    log(f"⬆️  Pushing image to Artifact Registry...")
    run_cmd(["docker", "push", image_tag], log_cb=log_cb)

    # ── 6. Deploy to Cloud Run ─────────────────────────────────────────────────
    log(f"🚀 Deploying to Cloud Run ({region})...")
    run_cmd([
        "gcloud", "run", "deploy", app_name,
        "--image", image_tag,
        "--region", region,
        "--platform", "managed",
        "--allow-unauthenticated",
        "--port", "8000",
        "--memory", "512Mi",
        "--project", project_id,
        "--quiet",
    ], log_cb=log_cb)

    # ── 7. Get service URL ─────────────────────────────────────────────────────
    import subprocess
    result = subprocess.run(
        ["gcloud", "run", "services", "describe", app_name,
         "--region", region, "--project", project_id,
         "--format", "value(status.url)"],
        capture_output=True, text=True,
    )
    url = result.stdout.strip() or f"https://{app_name}-<hash>-{region}.a.run.app"
    log(f"✅ Deployed! URL: {url}")
    return url


def _terraform_deploy(
    code_path: Path, project_id: str, region: str,
    env: dict, app_name: str, log_cb: Optional[LogCallback],
) -> str:
    log = log_cb or print
    tf_dir = code_path / "terraform"
    if not tf_dir.exists():
        raise DeployError(f"No terraform/ directory found in {code_path}")

    tf_env = {**env, "TF_VAR_project_id": project_id, "TF_VAR_region": region}

    log("🏗️  Running terraform init...")
    run_cmd(["terraform", "init"], cwd=tf_dir, env=tf_env, log_cb=log_cb)

    log("📋 Running terraform plan...")
    run_cmd(["terraform", "plan", "-out=tfplan"], cwd=tf_dir, env=tf_env, log_cb=log_cb)

    log("🚀 Running terraform apply...")
    run_cmd(["terraform", "apply", "-auto-approve", "tfplan"], cwd=tf_dir, env=tf_env, log_cb=log_cb)

    log("✅ Terraform apply complete!")
    return f"https://console.cloud.google.com/run?project={project_id}"
