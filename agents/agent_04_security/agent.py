"""Agent 04 — Security & Compliance Agent"""
from __future__ import annotations
import json
from agents.base_agent import BaseAgent
from agents.agent_04_security.prompts import JSON_SYSTEM, REPORT_SYSTEM, USER_TEMPLATE
from models.pipeline_state import PipelineState
from utils.file_utils import save_json, save_text, timestamped_name
from utils.json_parser import extract_json_with_retry
from utils.chunker import truncate


class SecurityAgent(BaseAgent):
    agent_id    = "agent_04_security"
    name        = "Security & Compliance Agent"
    model_tier        = "sonnet"
    max_output_tokens = 3072
    description = "STRIDE threat modelling, OWASP Top-10, GDPR/SOC2 compliance, security requirements"

    def run(self, state: PipelineState) -> PipelineState:
        # Recover architecture docs from disk if needed
        if not state.hld_document:
            state.hld_document = self._read_latest_output("architecture", "HLD_*.md")
        if not state.lld_document:
            state.lld_document = self._read_latest_output("architecture", "LLD_*.md")

        req = state.requirements_json or {}
        self.log("Running STRIDE threat modelling and OWASP review")

        user_msg = USER_TEMPLATE.format(
            project_name=state.project_name,
            tech_stack=json.dumps(req.get("tech_preferences", []), indent=2),
            hld=truncate(state.hld_document or "Not available", max_chars=6_000, label="HLD"),
            lld=truncate(state.lld_document or "Not available", max_chars=4_000, label="LLD"),
            nfr=json.dumps(req.get("non_functional_requirements", []), indent=2),
        )

        # ── Call 1: Structured JSON (no embedded code snippets) ──────────────
        self.log("Generating threat model & compliance JSON (1/2)")
        result = extract_json_with_retry(self._claude, JSON_SYSTEM, user_msg, fallback={})
        state.security_report = result

        # ── Call 2: Full Markdown security report ─────────────────────────────
        self.log("Generating security report Markdown (2/2)")
        report_system = REPORT_SYSTEM.format(project_name=state.project_name)
        report_md = self._claude.chat(
            system=report_system,
            messages=[{"role": "user", "content": user_msg}],
        )

        path = save_json(result, "security", timestamped_name("security_report", "json"))
        save_text(report_md, "security", timestamped_name("security_report", "md"))

        risk     = result.get("overall_risk_level", "unknown").upper()
        sec_reqs = len(result.get("security_requirements", []))
        threats  = sum(len(v) for v in result.get("threat_model", {}).values() if isinstance(v, list))

        self.last_summary     = f"Risk: {risk} | {threats} threats | {sec_reqs} security requirements"
        self.last_output_path = str(path)
        self.log(self.last_summary)
        return state
