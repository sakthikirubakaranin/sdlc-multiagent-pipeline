"""
Credentials Manager
────────────────────
Stores cloud + GitHub credentials locally in .credentials.json (gitignored).
Never committed to source control.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from loguru import logger

CREDS_FILE = Path(__file__).parent.parent / ".credentials.json"


class GCPCredentials(BaseModel):
    project_id:           str = ""
    region:               str = "us-central1"
    service_account_json: str = ""   # full JSON string of the SA key
    artifact_registry:    str = ""   # e.g. us-central1-docker.pkg.dev

class AWSCredentials(BaseModel):
    access_key_id:     str = ""
    secret_access_key: str = ""
    region:            str = "us-east-1"
    account_id:        str = ""

class AzureCredentials(BaseModel):
    tenant_id:       str = ""
    client_id:       str = ""
    client_secret:   str = ""
    subscription_id: str = ""
    resource_group:  str = ""
    location:        str = "eastus"

class GitHubCredentials(BaseModel):
    token:    str = ""
    username: str = ""
    repo_url: str = ""   # e.g. https://github.com/username/repo-name


class AllCredentials(BaseModel):
    gcp:    GCPCredentials    = Field(default_factory=GCPCredentials)
    aws:    AWSCredentials    = Field(default_factory=AWSCredentials)
    azure:  AzureCredentials  = Field(default_factory=AzureCredentials)
    github: GitHubCredentials = Field(default_factory=GitHubCredentials)


def load_credentials() -> AllCredentials:
    if CREDS_FILE.exists():
        try:
            data = json.loads(CREDS_FILE.read_text())
            return AllCredentials.model_validate(data)
        except Exception as e:
            logger.warning(f"Could not load credentials: {e}")
    return AllCredentials()


def save_credentials(creds: AllCredentials) -> None:
    CREDS_FILE.write_text(
        json.dumps(creds.model_dump(), indent=2),
        encoding="utf-8",
    )
    logger.info(f"Credentials saved to {CREDS_FILE}")


def get_creds_for_provider(provider: str) -> dict:
    """Return the relevant credentials dict for a given cloud provider."""
    creds = load_credentials()
    if provider == "gcp":
        return creds.gcp.model_dump()
    elif provider == "aws":
        return creds.aws.model_dump()
    elif provider == "azure":
        return creds.azure.model_dump()
    elif provider == "github":
        return creds.github.model_dump()
    return {}
