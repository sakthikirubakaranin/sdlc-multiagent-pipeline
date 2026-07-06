"""Agent 09 — Deployment Agent"""
from __future__ import annotations
import json
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.agent_09_deployment.prompts import (
    TERRAFORM_SYSTEM, CICD_SYSTEM, K8S_SYSTEM, RUNBOOK_SYSTEM,
    LOCALHOST_SYSTEM, CONTEXT_TEMPLATE,
)
from models.pipeline_state import PipelineState
from utils.file_utils import outputs_path
from utils.chunker import truncate


class DeploymentAgent(BaseAgent):
    agent_id    = "agent_09_deployment"
    name        = "Deployment Agent"
    model_tier        = "sonnet"
    max_output_tokens = 8192
    description = "Generates GCP Terraform, K8s manifests, CI/CD pipelines"

    def run(self, state: PipelineState) -> PipelineState:
        review = state.review_report or {}
        gate   = review.get("gate_passed", True)
        score  = review.get("overall_score", "N/A")

        if not gate:
            self.log(f"⚠ Review gate FAILED (score={score}) — generating deployment config with caution notice")

        tech_stack: dict = {}
        try:
            ts_files = sorted(Path(str(outputs_path("architecture", ""))).glob("tech_stack_*.json"))
            if ts_files:
                tech_stack = json.loads(ts_files[-1].read_text())
        except Exception:
            pass

        if not state.prd_document:
            state.prd_document = self._read_latest_output("requirements", "PRD_*.md")

        is_localhost = state.cloud_provider == "localhost"
        call_count = "2" if is_localhost else "4"
        provider_label = "localhost Docker" if is_localhost else state.cloud_provider.upper()
        self.log(f"Generating {provider_label} deployment infrastructure ({call_count} calls)")
        ctx = CONTEXT_TEMPLATE.format(
            project_name=state.project_name,
            cloud_provider="localhost (Docker)" if is_localhost else state.cloud_provider.upper(),
            gate_passed=gate,
            score=score,
            prd_summary=truncate(state.prd_document or "", max_chars=2_000, label="PRD"),
            tech_stack=json.dumps(tech_stack, indent=2),
            required_fixes=json.dumps(review.get("required_fixes", [])[:5], indent=2),
        )

        all_files: dict[str, str] = {}
        base = outputs_path("deployments", "")

        if is_localhost:
            # ── Localhost: Docker Compose + scripts ───────────────────────────
            self.log("Generating Docker Compose local setup (1/2)")
            all_files.update(self._generate_delimited_files(LOCALHOST_SYSTEM, ctx))
            self.log("Generating local runbooks (2/2)")
            all_files.update(self._generate_delimited_files(RUNBOOK_SYSTEM, ctx))
        else:
            # ── Cloud: Terraform + CI/CD + K8s + Runbooks ────────────────────
            self.log("Generating Terraform IaC (1/4)")
            all_files.update(self._generate_delimited_files(TERRAFORM_SYSTEM, ctx))
            self.log("Generating CI/CD pipelines (2/4)")
            all_files.update(self._generate_delimited_files(CICD_SYSTEM, ctx))
            self.log("Generating Kubernetes manifests (3/4)")
            all_files.update(self._generate_delimited_files(K8S_SYSTEM, ctx))
            self.log("Generating deployment runbooks (4/4)")
            all_files.update(self._generate_delimited_files(RUNBOOK_SYSTEM, ctx))

        state.deployment_config = {
            "provider":      state.cloud_provider,
            "environments":  {"local": {}} if is_localhost else {"dev": {}, "staging": {}, "prod": {}},
            "iac_files":     {k: v for k, v in all_files.items() if k.startswith("terraform/")},
            "cicd_files":    {k: v for k, v in all_files.items() if k.startswith(".github/") or k.startswith("scripts/")},
            "k8s_manifests": {k: v for k, v in all_files.items() if k.startswith("k8s/")},
        }

        written = 0
        for rel_path, content in all_files.items():
            try:
                fp = base / rel_path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                written += 1
            except Exception as exc:
                self.log(f"Warning: could not write {rel_path}: {exc}")

        tf_count  = sum(1 for k in all_files if k.startswith("terraform/") and k.endswith(".tf"))
        k8s_count = sum(1 for k in all_files if k.startswith("k8s/"))

        self.last_summary = (
            f"{state.cloud_provider.upper()} | {written} files | "
            + (f"docker-compose + scripts" if is_localhost else f"{tf_count} Terraform + {k8s_count} K8s manifests")
        )
        self.last_output_path = str(base)
        self.log(self.last_summary)
        return state
