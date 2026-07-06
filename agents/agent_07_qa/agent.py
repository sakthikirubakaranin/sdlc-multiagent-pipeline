"""Agent 07 — QA & Test Automation Agent"""
from __future__ import annotations
import json
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.agent_07_qa.prompts import (
    TEST_PLAN_SYSTEM, UNIT_SYSTEM, INTEGRATION_SYSTEM, INFRA_TEST_SYSTEM, CONTEXT_TEMPLATE,
)
from models.pipeline_state import PipelineState
from utils.file_utils import save_text, outputs_path, timestamped_name
from utils.chunker import summarise_files, truncate


class QAAgent(BaseAgent):
    agent_id    = "agent_07_qa"
    name        = "QA & Test Automation Agent"
    model_tier        = "haiku"
    max_output_tokens = 4096
    description = "Generates unit, integration, E2E, BDD, and performance tests"

    def run(self, state: PipelineState) -> PipelineState:
        req        = state.requirements_json or {}
        code_files = state.generated_code    or {}

        # Recover architecture files from disk if needed
        if not state.openapi_spec:
            state.openapi_spec = self._read_latest_output("architecture", "openapi_*.yaml")

        tech_stack: dict = {}
        try:
            ts_files = sorted(Path(str(outputs_path("architecture", ""))).glob("tech_stack_*.json"))
            if ts_files:
                tech_stack = json.loads(ts_files[-1].read_text())
        except Exception:
            pass

        language  = tech_stack.get("language",  "Python")
        framework = tech_stack.get("framework", "FastAPI")
        self.log(f"Generating test suite (4 calls)")

        ctx = CONTEXT_TEMPLATE.format(
            project_name=state.project_name,
            language=language,
            framework=framework,
            functional_reqs=json.dumps(req.get("functional_requirements", [])[:15], indent=2),
            nfr_reqs=json.dumps(req.get("non_functional_requirements", []), indent=2),
            openapi=truncate(state.openapi_spec or "", max_chars=3_000, label="OpenAPI"),
            code_summary=summarise_files(code_files, max_files=15),
        )

        all_files: dict[str, str] = {}
        base = outputs_path("tests", "")

        # ── Call 1: Test plan (plain markdown) ───────────────────────────────
        self.log("Generating test plan (1/4)")
        plan_system = TEST_PLAN_SYSTEM.format(project_name=state.project_name)
        test_plan   = self._claude.chat(system=plan_system, messages=[{"role": "user", "content": ctx}])
        save_text(test_plan, "tests", timestamped_name("TEST_PLAN", "md"))

        # ── Call 2: Unit tests ────────────────────────────────────────────────
        self.log("Generating unit tests (2/4)")
        unit_system = UNIT_SYSTEM.format(framework=framework)
        all_files.update(self._generate_delimited_files(unit_system, ctx))

        # ── Call 3: Integration tests ─────────────────────────────────────────
        self.log("Generating integration tests (3/4)")
        int_system = INTEGRATION_SYSTEM.format(framework=framework)
        all_files.update(self._generate_delimited_files(int_system, ctx))

        # ── Call 4: Performance, E2E, BDD, CI config ──────────────────────────
        self.log("Generating performance & CI test config (4/4)")
        all_files.update(self._generate_delimited_files(INFRA_TEST_SYSTEM, ctx))

        state.test_suite = {"files": list(all_files.keys())}

        # Write all test files
        written = 0
        for rel_path, content in all_files.items():
            try:
                fp = base / rel_path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                written += 1
            except Exception as exc:
                self.log(f"Warning: could not write {rel_path}: {exc}")

        unit_count = sum(1 for k in all_files if "unit" in k)
        int_count  = sum(1 for k in all_files if "integration" in k)
        e2e_count  = sum(1 for k in all_files if "e2e" in k)
        bdd_count  = sum(1 for k in all_files if ".feature" in k)

        self.last_summary     = f"{written} test files | {unit_count} unit, {int_count} integration, {e2e_count} E2E, {bdd_count} BDD"
        self.last_output_path = str(base)
        self.log(self.last_summary)
        return state
