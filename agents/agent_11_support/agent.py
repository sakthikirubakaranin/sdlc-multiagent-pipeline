"""Agent 11 — Support & Maintenance Agent"""
from __future__ import annotations
import json
from agents.base_agent import BaseAgent
from models.pipeline_state import PipelineState
from utils.file_utils import save_text, save_json, timestamped_name
from utils.json_parser import extract_json_with_retry

FILE_FORMAT = """
Return ONLY files in this exact format:

=== FILE: filename.md ===
<full file content>

No JSON wrapper, no fences, no explanation outside file blocks.
"""

RUNBOOK_SYSTEM = """
You are the Support & Maintenance Agent. Generate operational support documentation.

Files to generate:
- SUPPORT_RUNBOOK.md      (system overview, contacts, accessing system, common user issues + solutions, admin tasks, log locations, dashboard links)
- INCIDENT_RESPONSE.md    (severity P0-P3 definitions, detection, triage, communication template, resolution steps, blameless postmortem template)
- FAQ.md                  (at least 15 Q&As: deployment, scaling, monitoring, user mgmt, backups, data exports, performance, troubleshooting)
- SLA_REPORT_TEMPLATE.md  (monthly SLA report: uptime %, latency percentiles, error rates, incidents summary, action items)
- DEPENDENCY_UPDATE_PLAN.md (checklist: how to check for updates, test procedure, staged rollout, rollback)
""" + FILE_FORMAT

STRUCTURED_SYSTEM = """
You are the Support & Maintenance Agent. Return a JSON object:

{
  "known_issues": [{"id":"KI-001","title":"...","description":"...","workaround":"step-by-step","root_cause":"...","eta_fix":"sprint N / unknown","severity":"high|medium|low","affected_users":"..."}],
  "maintenance_schedule": {
    "daily":     [{"task":"...","owner":"...","estimated_time":"15m","how_to":"..."}],
    "weekly":    [{"task":"...","owner":"...","estimated_time":"30m","how_to":"..."}],
    "monthly":   [{"task":"...","owner":"...","estimated_time":"2h","how_to":"..."}],
    "quarterly": [{"task":"...","owner":"...","estimated_time":"4h","how_to":"..."}]
  },
  "feedback_for_next_sprint": [{"id":"FB-001","type":"enhancement|bug|tech_debt|security|performance","title":"...","description":"...","priority":"high|medium|low","source":"gap_analysis|code_review|nfr|security_report"}],
  "escalation_matrix": [{"level":"L1|L2|L3","role":"...","trigger":"...","contact_method":"Slack / PagerDuty / email","response_time_target":"..."}]
}

Return ONLY the JSON object. No fences.
"""


class SupportAgent(BaseAgent):
    agent_id    = "agent_11_support"
    name        = "Support & Maintenance Agent"
    model_tier        = "haiku"
    max_output_tokens = 2048
    description = "Runbooks, incident response, maintenance schedule, sprint feedback, FAQ, SLA reporting"

    def run(self, state: PipelineState) -> PipelineState:
        gap    = state.gap_analysis    or {}
        review = state.review_report   or {}
        monitor = state.monitoring_config or {}

        stage_feedback = []
        if gap.get("risks"):
            stage_feedback.append(f"Analysis risks: {len(gap['risks'])} identified")
        if review.get("required_fixes"):
            stage_feedback.extend([f"Review: {f}" for f in review["required_fixes"][:3]])

        self.log("Generating support & maintenance package (2 calls)")

        ctx = f"""
Project: {state.project_name}
Cloud: {state.cloud_provider.upper()}

--- OPEN RISKS ---
{json.dumps(gap.get("risks", [])[:8], indent=2)}

--- HIGH-SEVERITY REVIEW ISSUES ---
{json.dumps([i for i in review.get("issues", []) if i.get("severity") in ("critical","high")][:8], indent=2)}

--- SLA TARGETS ---
{json.dumps(monitor.get("sla_definitions", {}), indent=2)}

--- FEEDBACK FROM PREVIOUS STAGES ---
{chr(10).join(stage_feedback)}
"""

        # ── Call 1: Markdown support docs ─────────────────────────────────────
        self.log("Generating support documentation (1/2)")
        doc_files: dict[str, str] = self._generate_delimited_files(RUNBOOK_SYSTEM, ctx)

        for filename, content in doc_files.items():
            save_text(content, "docs", filename)

        # ── Call 2: Structured JSON (small — safe) ────────────────────────────
        self.log("Generating maintenance schedule & known issues JSON (2/2)")
        result = extract_json_with_retry(self._claude, STRUCTURED_SYSTEM, ctx, fallback={})
        state.support_log = [result]

        save_json(result.get("maintenance_schedule", {}),     "docs", "MAINTENANCE_SCHEDULE.json")
        save_json(result.get("known_issues", []),             "docs", timestamped_name("known_issues", "json"))
        save_json(result.get("escalation_matrix", []),        "docs", "ESCALATION_MATRIX.json")
        save_json(result.get("feedback_for_next_sprint", []), "docs", timestamped_name("sprint_feedback", "json"))

        feedback_count = len(result.get("feedback_for_next_sprint", []))
        ki_count       = len(result.get("known_issues", []))
        maint_tasks    = sum(
            len(v) for v in result.get("maintenance_schedule", {}).values()
            if isinstance(v, list)
        )
        doc_count = len(doc_files)

        self.last_summary = (
            f"{doc_count} docs | {ki_count} known issues | "
            f"{maint_tasks} maintenance tasks | {feedback_count} items for next sprint"
        )
        self.last_output_path = "outputs/docs/SUPPORT_RUNBOOK.md"
        self.log(self.last_summary)
        return state
