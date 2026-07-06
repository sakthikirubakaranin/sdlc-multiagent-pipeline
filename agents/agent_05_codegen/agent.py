"""Agent 05 — Code Generation Agent"""
from __future__ import annotations
import json
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.agent_05_codegen.prompts import (
    CORE_SYSTEM, ROUTES_SYSTEM, INFRA_SYSTEM, CONTEXT_TEMPLATE,
)
from models.pipeline_state import PipelineState
from utils.file_utils import save_json, outputs_path, timestamped_name
from utils.chunker import truncate


class CodeGenAgent(BaseAgent):
    agent_id    = "agent_05_codegen"
    name        = "Code Generation Agent"
    model_tier        = "sonnet"
    max_output_tokens = 8192
    description = "Generates production-ready source code using plain-text file delimiter format"

    def run(self, state: PipelineState) -> PipelineState:
        # Recover from disk if state fields lost between runs
        if not state.lld_document:
            state.lld_document = self._read_latest_output("architecture", "LLD_*.md")
        if not state.openapi_spec:
            state.openapi_spec = self._read_latest_output("architecture", "openapi_*.yaml")
        if not state.schema_document:
            state.schema_document = self._read_latest_output("architecture", "schema_*.sql")
        if not state.lld_document:
            raise ValueError("No LLD — run ArchitectureAgent first")

        req      = state.requirements_json or {}
        security = state.security_report   or {}

        # Load tech stack from saved JSON
        tech_stack: dict = {}
        try:
            ts_files = sorted(Path(str(outputs_path("architecture", ""))).glob("tech_stack_*.json"))
            if ts_files:
                tech_stack = json.loads(ts_files[-1].read_text())
        except Exception:
            pass

        language  = tech_stack.get("language",  "Python")
        framework = tech_stack.get("framework", "FastAPI")
        cloud     = state.cloud_provider or "localhost"
        self.log(f"Generating {language}/{framework} code for {cloud} (3 calls)")

        ctx = CONTEXT_TEMPLATE.format(
            project_name=state.project_name,
            language=language,
            framework=framework,
            cloud=cloud,
            # Give Claude more schema/LLD context so it derives correct domain models
            lld=truncate(state.lld_document,   max_chars=10_000, label="LLD"),
            schema=truncate(state.schema_document, max_chars=6_000, label="Schema"),
            openapi=truncate(state.openapi_spec,   max_chars=5_000, label="OpenAPI"),
            security_reqs=json.dumps(security.get("security_requirements", [])[:10], indent=2),
            # Include ALL functional requirements so Claude knows all features to implement
            functional_reqs=json.dumps(req.get("functional_requirements", []), indent=2),
        )

        # Inject framework into each system prompt so Claude knows the tech stack
        core_system   = CORE_SYSTEM.format(framework=framework)
        routes_system = ROUTES_SYSTEM.format(framework=framework)
        infra_system  = INFRA_SYSTEM.format(framework=framework)

        all_files: dict[str, str] = {}

        # ── Call 1: Core app + domain models ─────────────────────────────────
        self.log("Generating core app + domain models (1/3)")
        all_files.update(self._generate_delimited_files(core_system, ctx))

        # ── Call 2: Routes & Pydantic schemas ────────────────────────────────
        self.log("Generating routes & schemas (2/3)")
        all_files.update(self._generate_delimited_files(routes_system, ctx))

        # ── Call 3: Services, Dockerfile & infra ─────────────────────────────
        self.log("Generating services & infra files (3/3)")
        all_files.update(self._generate_delimited_files(infra_system, ctx))

        state.generated_code = all_files

        # Write all files to outputs/code/
        base = outputs_path("code", "")
        written = 0
        for rel_path, content in all_files.items():
            try:
                fp = base / rel_path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                written += 1
            except Exception as exc:
                self.log(f"Warning: could not write {rel_path}: {exc}")

        manifest = {
            "files": list(all_files.keys()),
            "language": language,
            "framework": framework,
            "cloud": cloud,
            "total_files": written,
        }
        save_json(manifest, "code", timestamped_name("code_manifest", "json"))

        self.last_summary     = f"Generated {written} files | {language}/{framework} → {cloud}"
        self.last_output_path = str(base)
        self.log(self.last_summary)
        return state
