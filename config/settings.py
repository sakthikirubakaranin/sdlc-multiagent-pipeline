from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "SDLC Agent Pipeline"
    app_env: Literal["development", "staging", "production"] = "development"
    app_log_level: str = "INFO"
    secret_key: str = "change_me"

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 8192

    # ── API Server ────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./sdlc_pipeline.db"

    # ── Cloud ─────────────────────────────────────────────────────────────────
    cloud_provider: Literal["aws", "gcp", "azure"] = "aws"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    google_application_credentials: str = ""
    gcp_project_id: str = ""
    azure_subscription_id: str = ""
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # ── Outputs ───────────────────────────────────────────────────────────────
    outputs_dir: str = "./outputs"

    # ── Whisper ───────────────────────────────────────────────────────────────
    whisper_model: Literal["tiny", "base", "small", "medium", "large"] = "base"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
