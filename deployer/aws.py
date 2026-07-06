"""AWS deployer — ECS Fargate via ECR + Terraform or direct ECS update."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Optional
from .base import run_cmd, DeployError, LogCallback


def deploy(
    code_path: Path,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    account_id: str,
    app_name: str = "sdlc-app",
    use_terraform: bool = True,
    log_cb: Optional[LogCallback] = None,
) -> str:
    log = log_cb or print

    if not access_key_id or not secret_access_key:
        raise DeployError("AWS Access Key ID and Secret Access Key are required. Set them in Settings → Credentials → AWS.")
    if not account_id:
        raise DeployError("AWS Account ID is required.")

    env = {
        "AWS_ACCESS_KEY_ID":     access_key_id,
        "AWS_SECRET_ACCESS_KEY": secret_access_key,
        "AWS_DEFAULT_REGION":    region,
    }

    # ── 1. Verify credentials ──────────────────────────────────────────────────
    log("🔑 Verifying AWS credentials...")
    run_cmd(["aws", "sts", "get-caller-identity"], env=env, log_cb=log_cb)

    ecr_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{app_name}"
    image_tag = f"{ecr_uri}:latest"

    # ── 2. Create ECR repo ─────────────────────────────────────────────────────
    log(f"📦 Creating ECR repository: {app_name}")
    try:
        run_cmd([
            "aws", "ecr", "create-repository",
            "--repository-name", app_name,
            "--region", region,
        ], env=env, log_cb=log_cb)
    except Exception:
        log("   (ECR repo may already exist — continuing)")

    # ── 3. Docker login to ECR ─────────────────────────────────────────────────
    log("🐳 Logging Docker into ECR...")
    token_result = subprocess.run(
        ["aws", "ecr", "get-login-password", "--region", region],
        capture_output=True, text=True, env={**__import__("os").environ, **env},
    )
    docker_pass = token_result.stdout.strip()
    run_cmd([
        "docker", "login", "--username", "AWS",
        "--password-stdin", f"{account_id}.dkr.ecr.{region}.amazonaws.com",
    ], env={**__import__("os").environ, "DOCKER_PASSWORD": docker_pass},
       log_cb=log_cb)

    # ── 4. Build & Push ────────────────────────────────────────────────────────
    log(f"🏗️  Building Docker image: {image_tag}")
    run_cmd(["docker", "build", "-t", image_tag, "."], cwd=code_path, log_cb=log_cb)

    log("⬆️  Pushing image to ECR...")
    run_cmd(["docker", "push", image_tag], env=env, log_cb=log_cb)

    if use_terraform:
        return _terraform_deploy(code_path, region, account_id, app_name, image_tag, env, log_cb)
    else:
        log("✅ Image pushed. Use ECS console or terraform to update the service.")
        return f"https://console.aws.amazon.com/ecs/home?region={region}"


def _terraform_deploy(
    code_path: Path, region: str, account_id: str,
    app_name: str, image_tag: str, env: dict, log_cb: Optional[LogCallback],
) -> str:
    log = log_cb or print
    tf_dir = code_path / "terraform"
    if not tf_dir.exists():
        raise DeployError(f"No terraform/ directory in {code_path}")

    tf_env = {
        **env,
        "TF_VAR_region":      region,
        "TF_VAR_account_id":  account_id,
        "TF_VAR_app_name":    app_name,
        "TF_VAR_image_uri":   image_tag,
    }

    log("🏗️  terraform init...")
    run_cmd(["terraform", "init"], cwd=tf_dir, env=tf_env, log_cb=log_cb)
    log("🚀 terraform apply...")
    run_cmd(["terraform", "apply", "-auto-approve"], cwd=tf_dir, env=tf_env, log_cb=log_cb)
    log("✅ AWS deployment complete!")
    return f"https://console.aws.amazon.com/ecs/home?region={region}#/clusters"
