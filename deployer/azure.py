"""Azure deployer — Container Apps via ACR + Terraform or direct az deploy."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from .base import run_cmd, DeployError, LogCallback


def deploy(
    code_path: Path,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subscription_id: str,
    resource_group: str,
    location: str = "eastus",
    app_name: str = "sdlc-app",
    use_terraform: bool = True,
    log_cb: Optional[LogCallback] = None,
) -> str:
    log = log_cb or print

    if not tenant_id or not client_id or not client_secret:
        raise DeployError("Azure Tenant ID, Client ID, and Client Secret are required. Set them in Settings → Credentials → Azure.")
    if not subscription_id:
        raise DeployError("Azure Subscription ID is required.")

    acr_name = f"{app_name.replace('-', '')}acr"
    acr_login_server = f"{acr_name}.azurecr.io"
    image_tag = f"{acr_login_server}/{app_name}:latest"

    # ── 1. Login ───────────────────────────────────────────────────────────────
    log("🔑 Logging in to Azure with service principal...")
    run_cmd([
        "az", "login", "--service-principal",
        "--tenant", tenant_id,
        "--username", client_id,
        "--password", client_secret,
    ], log_cb=log_cb)
    run_cmd(["az", "account", "set", "--subscription", subscription_id], log_cb=log_cb)

    # ── 2. Create resource group ───────────────────────────────────────────────
    log(f"📦 Ensuring resource group '{resource_group}' exists...")
    run_cmd([
        "az", "group", "create",
        "--name", resource_group,
        "--location", location,
    ], log_cb=log_cb)

    # ── 3. Create ACR ─────────────────────────────────────────────────────────
    log(f"📦 Creating/verifying Azure Container Registry '{acr_name}'...")
    try:
        run_cmd([
            "az", "acr", "create",
            "--resource-group", resource_group,
            "--name", acr_name,
            "--sku", "Basic",
            "--admin-enabled", "true",
        ], log_cb=log_cb)
    except Exception:
        log("   (ACR may already exist — continuing)")

    # ── 4. Docker login to ACR ─────────────────────────────────────────────────
    log("🐳 Logging Docker into ACR...")
    run_cmd(["az", "acr", "login", "--name", acr_name], log_cb=log_cb)

    # ── 5. Build & Push ────────────────────────────────────────────────────────
    log(f"🏗️  Building Docker image: {image_tag}")
    run_cmd(["docker", "build", "-t", image_tag, "."], cwd=code_path, log_cb=log_cb)

    log("⬆️  Pushing image to ACR...")
    run_cmd(["docker", "push", image_tag], log_cb=log_cb)

    if use_terraform:
        return _terraform_deploy(code_path, subscription_id, resource_group, location, app_name, image_tag, log_cb)
    else:
        # Direct Container Apps deploy
        log("🚀 Deploying to Azure Container Apps...")
        run_cmd([
            "az", "containerapp", "create",
            "--name", app_name,
            "--resource-group", resource_group,
            "--image", image_tag,
            "--target-port", "8000",
            "--ingress", "external",
            "--registry-server", acr_login_server,
        ], log_cb=log_cb)
        log("✅ Azure deployment complete!")
        return f"https://portal.azure.com/#resource/subscriptions/{subscription_id}/resourceGroups/{resource_group}"


def _terraform_deploy(
    code_path: Path, subscription_id: str, resource_group: str,
    location: str, app_name: str, image_tag: str, log_cb: Optional[LogCallback],
) -> str:
    log = log_cb or print
    tf_dir = code_path / "terraform"
    if not tf_dir.exists():
        raise DeployError(f"No terraform/ directory in {code_path}")

    tf_env = {
        "TF_VAR_subscription_id":  subscription_id,
        "TF_VAR_resource_group":   resource_group,
        "TF_VAR_location":         location,
        "TF_VAR_app_name":         app_name,
        "TF_VAR_image_uri":        image_tag,
    }

    log("🏗️  terraform init...")
    run_cmd(["terraform", "init"], cwd=tf_dir, env=tf_env, log_cb=log_cb)
    log("🚀 terraform apply...")
    run_cmd(["terraform", "apply", "-auto-approve"], cwd=tf_dir, env=tf_env, log_cb=log_cb)
    log("✅ Azure Terraform deployment complete!")
    return f"https://portal.azure.com"
