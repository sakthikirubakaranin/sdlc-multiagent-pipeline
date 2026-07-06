"""Agent 08 — Code Review Agent"""
from __future__ import annotations
import json
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.agent_08_review.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from models.pipeline_state import PipelineState
from utils.file_utils import save_json, save_text, outputs_path, timestamped_name
from utils.json_parser import extract_json_with_retry
from utils.chunker import summarise_files


class ReviewAgent(BaseAgent):
    agent_id    = "agent_08_review"
    name        = "Code Review Agent"
    model_tier        = "haiku"
    max_output_tokens = 2048
    description = "Automated PR-style code review with quality gate, security findings, and metrics"

    def run(self, state: PipelineState) -> PipelineState:
        security = state.security_report or {}
        code_files = state.generated_code or {}
        test_suite = state.test_suite or {}

        # Load ADRs if available
        adrs = []
        try:
            adr_files = list(Path(str(outputs_path("docs", ""))).glob("ADRs_*.json"))
            if adr_files:
                adrs = json.loads(adr_files[-1].read_text())
        except Exception:
            pass

        test_files = list(test_suite.get("unit_tests", {}).keys()) + \
                     list(test_suite.get("integration_tests", {}).keys())

        self.log(f"Reviewing {len(code_files)} code files against {len(test_files)} test files")

        user_msg = USER_TEMPLATE.format(
            project_name=state.project_name,
            code_summary=summarise_files(code_files, max_chars_each=1000, max_files=12),
            security_reqs=json.dumps(security.get("security_requirements", [])[:15], indent=2),
            test_summary="\n".join(f"• {f}" for f in test_files[:20]),
            adrs=json.dumps(adrs[:5], indent=2),
        )

        result = extract_json_with_retry(self._claude, SYSTEM_PROMPT, user_msg, fallback={})
        state.review_report = result

        path = save_json(result, "docs", timestamped_name("code_review", "json"))
        save_text(self._format_md(result), "docs", timestamped_name("CODE_REVIEW", "md"))

        score     = result.get("overall_score", 0)
        gate      = result.get("gate_passed", False)
        issues    = len(result.get("issues", []))
        criticals = sum(1 for i in result.get("issues", []) if i.get("severity") == "critical")

        self.last_summary     = (
            f"Score: {score}/100 | Gate: {'✔ PASSED' if gate else '✖ FAILED'} | "
            f"{issues} issues ({criticals} critical)"
        )
        self.last_output_path = str(path)
        self.log(self.last_summary)
        return state

    def _format_md(self, r: dict) -> str:
        gate = r.get("gate_passed", False)
        lines = [
            f"# Code Review Report",
            f"**Score:** {r.get('overall_score', '?')}/100 &nbsp; | &nbsp; "
            f"**Gate:** {'✅ PASSED' if gate else '❌ FAILED'}\n",
            f"## Executive Summary\n{r.get('executive_summary', '')}\n",
            "## Metrics\n",
        ]
        m = r.get("metrics", {})
        for k, v in m.items():
            lines.append(f"- **{k.replace('_',' ').title()}:** {v}")
        lines.append("\n## Issues\n")
        for issue in sorted(r.get("issues", []), key=lambda x: {"critical":0,"high":1,"medium":2,"low":3,"info":4}.get(x.get("severity","info"),4)):
            sev = issue.get("severity","").upper()
            lines.append(f"### [{sev}] {issue.get('title','')} — `{issue.get('file','')}:{issue.get('line_range','')}`")
            lines.append(f"{issue.get('description','')}\n")
            if issue.get("suggestion"):
                lines.append(f"**Fix:** {issue['suggestion']}\n")
        lines.append("\n## Required Fixes\n")
        for fix in r.get("required_fixes", []):
            lines.append(f"- {fix}")
        lines.append("\n## What's Good ✅\n")
        for pos in r.get("positive_feedback", []):
            lines.append(f"- {pos}")
        return "\n".join(lines)
