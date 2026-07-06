"""Agent 03 — Architecture & Design Agent"""
from __future__ import annotations
import json
from agents.base_agent import BaseAgent
from agents.agent_03_architecture.prompts import (
    CONTEXT_TEMPLATE,
    HLD_SYSTEM, LLD_SYSTEM, SCHEMA_SYSTEM, OPENAPI_SYSTEM, STRUCTURED_SYSTEM,
)
from models.pipeline_state import PipelineState
from utils.file_utils import save_text, save_json, timestamped_name
from utils.json_parser import extract_json_with_retry
from utils.chunker import truncate


class ArchitectureAgent(BaseAgent):
    agent_id    = "agent_03_architecture"
    name        = "Architecture & Design Agent"
    model_tier        = "sonnet"
    max_output_tokens = 8192
    description = "Generates HLD, LLD, SQL schema, OpenAPI spec, tech stack decisions"

    def run(self, state: PipelineState) -> PipelineState:
        # Recover PRD from disk if state field is empty (resume scenario)
        if not state.prd_document:
            state.prd_document = self._read_latest_output("requirements", "PRD_*.md")
        if not state.prd_document:
            raise ValueError("No PRD — run AnalysisAgent first")

        req = state.requirements_json or {}
        self.log("Generating architecture documents (5 calls)")

        # Shared context injected into every call
        ctx = CONTEXT_TEMPLATE.format(
            project_name=state.project_name,
            prd_excerpt=truncate(state.prd_document, max_chars=4_000, label="PRD"),
            functional_reqs=json.dumps(req.get("functional_requirements", [])[:20], indent=2),
            nfr_reqs=json.dumps(req.get("non_functional_requirements", []), indent=2),
            tech_prefs=json.dumps(req.get("tech_preferences", []), indent=2),
        )

        # ── Call 1: HLD ──────────────────────────────────────────────────────
        self.log("Generating HLD (1/5)")
        hld_system = HLD_SYSTEM.format(project_name=state.project_name)
        state.hld_document = self._claude.chat(
            system=hld_system,
            messages=[{"role": "user", "content": ctx}],
        )

        # ── Call 2: LLD ──────────────────────────────────────────────────────
        self.log("Generating LLD (2/5)")
        lld_system = LLD_SYSTEM.format(project_name=state.project_name)
        state.lld_document = self._claude.chat(
            system=lld_system,
            messages=[{"role": "user", "content": ctx}],
        )

        # ── Call 3: SQL Schema ────────────────────────────────────────────────
        self.log("Generating SQL schema (3/5)")
        state.schema_document = self._claude.chat(
            system=SCHEMA_SYSTEM,
            messages=[{"role": "user", "content": ctx}],
        )

        # ── Call 4: OpenAPI YAML ──────────────────────────────────────────────
        self.log("Generating OpenAPI spec (4/5)")
        state.openapi_spec = self._claude.chat(
            system=OPENAPI_SYSTEM,
            messages=[{"role": "user", "content": ctx}],
        )

        # ── Call 5: tech_stack + ADRs as JSON ────────────────────────────────
        self.log("Generating tech stack & ADRs JSON (5/5)")
        structured = extract_json_with_retry(
            self._claude, STRUCTURED_SYSTEM, ctx, fallback={}
        )

        # Persist to disk
        hld_path = save_text(state.hld_document,    "architecture", timestamped_name("HLD", "md"))
        save_text(state.lld_document,               "architecture", timestamped_name("LLD", "md"))
        save_text(state.schema_document,            "architecture", timestamped_name("schema", "sql"))
        save_text(state.openapi_spec,               "architecture", timestamped_name("openapi", "yaml"))
        save_json(structured.get("tech_stack", {}), "architecture", timestamped_name("tech_stack", "json"))
        save_json(structured.get("architecture_decisions", []), "architecture", timestamped_name("ADRs", "json"))

        ts       = structured.get("tech_stack", {})
        lang     = ts.get("language", "Python")
        framework = ts.get("framework", "FastAPI")
        adrs     = len(structured.get("architecture_decisions", []))

        self.last_summary     = f"HLD + LLD + Schema + OpenAPI generated | Stack: {lang}/{framework} | {adrs} ADRs"
        self.last_output_path = str(hld_path)
        self.log(self.last_summary)
        return state
