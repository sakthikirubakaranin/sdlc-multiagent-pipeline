"""Agent 02 — Requirements Analysis Agent"""
from __future__ import annotations
import json
from agents.base_agent import BaseAgent
from agents.agent_02_analysis.prompts import (
    PRD_SYSTEM_PROMPT, PRD_USER_TEMPLATE,
    ANALYSIS_SYSTEM_PROMPT, ANALYSIS_USER_TEMPLATE,
)
from models.pipeline_state import PipelineState
from utils.file_utils import save_json, save_text, timestamped_name
from utils.json_parser import extract_json_with_retry
from utils.chunker import truncate


class AnalysisAgent(BaseAgent):
    agent_id    = "agent_02_analysis"
    name        = "Requirements Analysis Agent"
    model_tier        = "sonnet"
    max_output_tokens = 4096
    description = "Gap analysis, MoSCoW prioritisation, and full PRD generation"

    def run(self, state: PipelineState) -> PipelineState:
        if not state.requirements_json:
            raise ValueError("No requirements_json — run IntakeAgent first")

        req_json     = state.requirements_json
        project_name = req_json.get("project_name", state.project_name)
        req_text     = truncate(json.dumps(req_json, indent=2), max_chars=50_000)

        n_fr  = len(req_json.get("functional_requirements", []))
        n_nfr = len(req_json.get("non_functional_requirements", []))
        self.log(f"Analysing {n_fr} FRs and {n_nfr} NFRs")

        # ── Call 1: PRD as plain Markdown (no JSON wrapping → no parse failures) ──
        self.log("Generating PRD document (call 1/2)")
        prd_system = PRD_SYSTEM_PROMPT.format(project_name=project_name)
        prd_user   = PRD_USER_TEMPLATE.format(
            project_name=project_name,
            requirements_json=req_text,
        )
        state.prd_document = self._claude.chat(system=prd_system, messages=[{"role": "user", "content": prd_user}])

        # ── Call 2: gap analysis + priorities + KPIs as JSON ─────────────────────
        self.log("Generating gap analysis & priorities (call 2/2)")
        analysis_user = ANALYSIS_USER_TEMPLATE.format(
            project_name=project_name,
            requirements_json=req_text,
        )
        result = extract_json_with_retry(self._claude, ANALYSIS_SYSTEM_PROMPT, analysis_user, fallback={})

        state.gap_analysis = result.get("gap_analysis", {})

        # Save artifacts
        prd_path = save_text(state.prd_document, "requirements", timestamped_name("PRD", "md"))
        save_json(state.gap_analysis, "requirements", timestamped_name("gap_analysis", "json"))
        save_json(result.get("prioritised_requirements", []), "requirements", timestamped_name("priorities", "json"))
        save_json(result.get("kpis", []), "requirements", timestamped_name("kpis", "json"))

        gaps      = len(state.gap_analysis.get("missing_info", []))
        conflicts = len(state.gap_analysis.get("conflicts", []))
        risks     = len(state.gap_analysis.get("risks", []))
        score     = state.gap_analysis.get("completeness_score", "?")

        self.last_summary     = f"PRD generated | Completeness: {score}% | {gaps} gaps, {conflicts} conflicts, {risks} risks"
        self.last_output_path = str(prd_path)
        self.log(self.last_summary)
        return state
