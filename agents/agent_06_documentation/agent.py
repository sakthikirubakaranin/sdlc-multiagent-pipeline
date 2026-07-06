"""Agent 06 — Code Documentation Agent"""
from __future__ import annotations
import json
from agents.base_agent import BaseAgent
from agents.agent_06_documentation.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from models.pipeline_state import PipelineState
from utils.file_utils import save_text, save_json, timestamped_name
from utils.json_parser import extract_json_with_retry
from utils.chunker import summarise_files, truncate


class DocumentationAgent(BaseAgent):
    agent_id    = "agent_06_documentation"
    name        = "Code Documentation Agent"
    model_tier        = "haiku"
    max_output_tokens = 4096
    description = "Generates README, API reference, developer guide, ADRs, changelog"

    def run(self, state: PipelineState) -> PipelineState:
        # Recover prose fields from disk if lost between resume runs
        if not state.hld_document:
            state.hld_document = self._read_latest_output("architecture", "HLD_*.md")
        if not state.openapi_spec:
            state.openapi_spec = self._read_latest_output("architecture", "openapi_*.yaml")

        self.log("Generating project documentation")

        code_files = state.generated_code or {}
        tech_stack = {}
        try:
            from pathlib import Path
            from utils.file_utils import outputs_path
            ts_files = list(Path(str(outputs_path("architecture", ""))).glob("tech_stack_*.json"))
            if ts_files:
                tech_stack = json.loads(ts_files[-1].read_text())
        except Exception:
            pass

        user_msg = USER_TEMPLATE.format(
            project_name=state.project_name,
            code_summary=summarise_files(code_files, max_files=20),
            openapi=truncate(state.openapi_spec or "", max_chars=4_000, label="OpenAPI"),
            hld_summary=truncate(state.hld_document or "", max_chars=3_000, label="HLD"),
            tech_stack=json.dumps(tech_stack, indent=2),
        )

        result = extract_json_with_retry(self._claude, SYSTEM_PROMPT, user_msg, fallback={})
        state.documentation = result

        readme_path = save_text(result.get("readme", ""),         "docs", "README.md")
        save_text(result.get("api_reference", ""),                 "docs", timestamped_name("API_REFERENCE", "md"))
        save_text(result.get("developer_guide", ""),               "docs", "DEVELOPER_GUIDE.md")
        save_text(result.get("changelog", ""),                     "docs", "CHANGELOG.md")
        save_text(result.get("env_vars_doc", ""),                  "docs", "ENV_VARS.md")
        save_json(result.get("adrs", []),                          "docs", timestamped_name("ADRs", "json"))

        adrs = len(result.get("adrs", []))
        self.last_summary     = f"README, API reference, developer guide, {adrs} ADRs, changelog generated"
        self.last_output_path = str(readme_path)
        self.log(self.last_summary)
        return state
