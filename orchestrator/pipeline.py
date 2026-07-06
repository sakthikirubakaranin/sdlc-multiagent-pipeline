"""
PipelineOrchestrator  (v2 — production)
────────────────────────────────────────
Runs all 12 SDLC agents in sequence, with:

  • State persistence   — snapshot saved to DB after every agent
  • Live event stream   — agent_started / agent_completed / agent_failed
  • Resume support      — restart from any agent (skips already-completed ones)
  • Per-agent retry     — configurable retries on transient failures
  • Cancellation        — set cancel_event to stop the run cleanly
  • Token tracking      — cumulative Claude API usage logged per run
  • Dry-run mode        — skip actual Claude calls (for testing the pipeline wiring)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from models.pipeline_state import PipelineState, AgentResult, AgentStatus
from orchestrator.events import event_bus
from orchestrator.state_manager import PipelineStateManager

# ── Agent imports ─────────────────────────────────────────────────────────────
from agents.agent_01_intake.agent        import IntakeAgent
from agents.agent_02_analysis.agent      import AnalysisAgent
from agents.agent_03_architecture.agent  import ArchitectureAgent
from agents.agent_04_security.agent      import SecurityAgent
from agents.agent_05_codegen.agent       import CodeGenAgent
from agents.agent_12_frontend.agent      import FrontendAgent        # ← moved to pos 6
from agents.agent_06_documentation.agent import DocumentationAgent   # ← now pos 7
from agents.agent_07_qa.agent            import QAAgent              # ← now pos 8
from agents.agent_08_review.agent        import ReviewAgent          # ← now pos 9
from agents.agent_09_deployment.agent    import DeploymentAgent      # ← now pos 10
from agents.agent_10_monitoring.agent    import MonitoringAgent      # ← now pos 11
from agents.agent_11_support.agent       import SupportAgent         # ← now pos 12
from agents.agent_13_packaging.agent     import PackagingAgent       # ← new pos 13

# ── Correct pipeline order ─────────────────────────────────────────────────────
# 1  Intake          — extract requirements from any format
# 2  Analysis        — PRD, gap analysis, priorities
# 3  Architecture    — HLD, LLD, schema, OpenAPI
# 4  Security        — STRIDE, OWASP, compliance
# 5  Code Gen        — backend source code
# 6  Frontend        — React/TS SPA (depends on backend API spec)
# 7  Documentation   — full-stack README, API reference, guide
# 8  QA & Testing    — tests for both backend AND frontend
# 9  Code Review     — quality gate on full codebase
# 10 Deployment      — docker-compose / Terraform for complete app
# 11 Monitoring      — Prometheus, Grafana, alerts
# 12 Support         — runbooks, incident response, SLA
# 13 Packaging       — bundles everything into a runnable artifact / DMG
AGENT_SEQUENCE = [
    IntakeAgent,
    AnalysisAgent,
    ArchitectureAgent,
    SecurityAgent,
    CodeGenAgent,
    FrontendAgent,
    DocumentationAgent,
    QAAgent,
    ReviewAgent,
    DeploymentAgent,
    MonitoringAgent,
    SupportAgent,
    PackagingAgent,
]

TOTAL_AGENTS = len(AGENT_SEQUENCE)


class PipelineOrchestrator:
    """
    Usage — full run:
        orchestrator = PipelineOrchestrator()
        await orchestrator.run(state)

    Usage — resume a failed run:
        state = PipelineStateManager.load_run(run_id)
        resume_from = PipelineStateManager.get_resume_index(state)
        await orchestrator.run(state, start_from=resume_from)

    Usage — dry run (no Claude calls):
        await orchestrator.run(state, dry_run=True)
    """

    def __init__(
        self,
        max_retries: int = 2,
        retry_delay: float = 3.0,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        self.max_retries   = max_retries
        self.retry_delay   = retry_delay
        self.cancel_event  = cancel_event or asyncio.Event()
        self._state_mgr    = PipelineStateManager()

    # ── Public entry point ────────────────────────────────────────────────────
    async def run(
        self,
        state: PipelineState,
        start_from: int = 0,
        stop_after: Optional[int] = None,
        dry_run: bool = False,
        skip_agents: Optional[list[str]] = None,
    ) -> PipelineState:
        """
        Execute the pipeline.

        Args:
            state:        Shared PipelineState (mutated in-place).
            start_from:   0-based index of the first agent to run.
            stop_after:   0-based index of the last agent to run (inclusive).
            dry_run:      If True, mock each agent's run() method.
            skip_agents:  List of agent_id strings to skip (mark SKIPPED).

        Returns:
            The final PipelineState after all agents complete (or fail).
        """
        from utils.claude_client import ClaudeClient
        ClaudeClient.reset()   # fresh cost counter per pipeline run

        run_id = state.run_id
        _skip  = set(skip_agents or [])
        agents_to_run = AGENT_SEQUENCE[
            start_from : (stop_after + 1 if stop_after is not None else None)
        ]

        # Scope all file outputs to outputs/{project_name}/
        from utils.file_utils import set_current_project
        set_current_project(state.project_name)

        logger.info(
            f"Pipeline starting | run_id={run_id} | project='{state.project_name}' "
            f"| agents={len(agents_to_run)} | start_from={start_from} | dry_run={dry_run}"
        )

        event_bus.pipeline_started(run_id, state.project_name, TOTAL_AGENTS)
        self._state_mgr.save_run(state)

        for rel_idx, AgentClass in enumerate(agents_to_run):
            abs_step = start_from + rel_idx + 1  # 1-based for display

            # ── Cancellation check ────────────────────────────────────────────
            if self.cancel_event.is_set():
                logger.warning(f"Pipeline cancelled before agent {abs_step}")
                event_bus.pipeline_cancelled(run_id, "User requested cancellation")
                break

            agent  = AgentClass()

            # ── Skip agent if requested ───────────────────────────────────────
            if agent.agent_id in _skip:
                logger.info(f"[{abs_step}/{TOTAL_AGENTS}] ⏭ SKIPPED: {agent.name}")
                event_bus.log(run_id, f"⏭ [{abs_step}/{TOTAL_AGENTS}] Skipped: {agent.name}")
                skipped_result = AgentResult(
                    agent_id   = agent.agent_id,
                    agent_name = agent.name,
                    status     = AgentStatus.SKIPPED,
                    started_at = datetime.now(timezone.utc),
                    completed_at = datetime.now(timezone.utc),
                )
                state.update_agent(skipped_result)
                self._state_mgr.save_agent_result(run_id, skipped_result)
                continue

            result = AgentResult(
                agent_id   = agent.agent_id,
                agent_name = agent.name,
                status     = AgentStatus.RUNNING,
                started_at = datetime.now(timezone.utc),
            )
            state.current_agent = agent.agent_id
            state.update_agent(result)

            event_bus.agent_started(run_id, agent.agent_id, agent.name, abs_step, TOTAL_AGENTS)
            self._state_mgr.save_agent_result(run_id, result)

            logger.info(f"[{abs_step}/{TOTAL_AGENTS}] ▶ {agent.name}")
            event_bus.log(run_id, f"[{abs_step}/{TOTAL_AGENTS}] Starting: {agent.name}")

            # ── Run with retry ────────────────────────────────────────────────
            success = False
            last_error: Optional[str] = None

            for attempt in range(1, self.max_retries + 2):  # +2: first attempt + retries
                try:
                    if dry_run:
                        state = self._mock_run(agent, state)
                    elif asyncio.iscoroutinefunction(agent.run):
                        state = await agent.run(state)
                    else:
                        state = await asyncio.to_thread(agent.run, state)

                    success = True
                    break

                except Exception as exc:
                    last_error = str(exc)
                    if attempt <= self.max_retries:
                        wait = self.retry_delay * attempt
                        logger.warning(
                            f"[{abs_step}/{TOTAL_AGENTS}] {agent.name} failed "
                            f"(attempt {attempt}/{self.max_retries + 1}): {exc}. "
                            f"Retrying in {wait}s…"
                        )
                        event_bus.log(
                            run_id,
                            f"⚠ {agent.name} attempt {attempt} failed: {exc}. Retrying in {wait}s…",
                            level="WARNING",
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"[{abs_step}/{TOTAL_AGENTS}] {agent.name} FAILED after {attempt} attempts: {exc}")

            # ── Update result ─────────────────────────────────────────────────
            result.completed_at = datetime.now(timezone.utc)

            if success:
                result.status      = AgentStatus.COMPLETED
                result.summary     = agent.last_summary or ""
                result.output_path = agent.last_output_path

                logger.success(f"[{abs_step}/{TOTAL_AGENTS}] ✔ {agent.name}: {result.summary}")
                event_bus.agent_completed(
                    run_id, agent.agent_id, agent.name,
                    abs_step, TOTAL_AGENTS,
                    result.summary or "", result.output_path,
                )
                event_bus.log(run_id, f"✔ [{abs_step}/{TOTAL_AGENTS}] {agent.name}: {result.summary}")

            else:
                result.status = AgentStatus.FAILED
                result.error  = last_error

                event_bus.agent_failed(run_id, agent.agent_id, agent.name, abs_step, TOTAL_AGENTS, last_error or "")
                event_bus.log(run_id, f"✖ [{abs_step}/{TOTAL_AGENTS}] {agent.name} FAILED: {last_error}", level="ERROR")

                state.update_agent(result)
                self._state_mgr.save_agent_result(run_id, result)
                self._state_mgr.save_run(state)

                # Stop the pipeline on any agent failure
                logger.error(f"Pipeline halted at step {abs_step} ({agent.name})")
                event_bus.pipeline_cancelled(run_id, f"Agent failed: {agent.name}")
                event_bus.send_done(run_id)
                return state

            state.update_agent(result)
            self._state_mgr.save_agent_result(run_id, result)
            self._state_mgr.save_run(state)   # Checkpoint after every agent

        # ── All agents done ───────────────────────────────────────────────────
        state.current_agent = None
        self._state_mgr.save_run(state)

        completed = sum(1 for r in state.agent_results if r.status == AgentStatus.COMPLETED)
        usage = ClaudeClient.get().usage_summary()
        cost_str = f"${usage['estimated_cost_usd']:.4f}"
        savings_str = f"${usage['estimated_savings_usd']:.4f}"
        logger.success(
            f"Pipeline complete | run_id={run_id} | "
            f"{completed}/{TOTAL_AGENTS} agents succeeded | "
            f"API cost ~{cost_str} | cache saved ~{savings_str}"
        )
        event_bus.pipeline_completed(run_id, TOTAL_AGENTS)
        event_bus.log(run_id, f"🎉 Pipeline complete — {completed}/{TOTAL_AGENTS} agents succeeded")
        event_bus.log(run_id, f"💰 Estimated API cost: {cost_str} | Cache savings: {savings_str}")
        event_bus.send_done(run_id)

        return state

    # ── Dry-run mock ──────────────────────────────────────────────────────────
    @staticmethod
    def _mock_run(agent, state: PipelineState) -> PipelineState:
        """
        Simulate an agent run without calling Claude.
        Populates just enough state so downstream agents don't crash.
        """
        logger.debug(f"[DRY-RUN] Mocking {agent.name}")
        agent.last_summary      = f"[DRY-RUN] {agent.name} completed (no Claude call)"
        agent.last_output_path  = None

        # Minimal state stubs per agent so the pipeline wiring holds together
        stubs = {
            "agent_01_intake":        lambda s: setattr(s, "requirements_json", {
                "project_name": s.project_name,
                "functional_requirements": [{"id": "FR-001", "title": "Stub requirement", "description": "Dry run stub"}],
                "non_functional_requirements": [],
                "constraints": [], "assumptions": [], "out_of_scope": [],
                "stakeholders": [], "tech_preferences": [], "timeline_hints": [], "raw_notes": "",
            }),
            "agent_02_analysis":      lambda s: (
                setattr(s, "prd_document", f"# PRD — {s.project_name}\n\n[DRY-RUN stub]"),
                setattr(s, "gap_analysis", {"ambiguities": [], "conflicts": [], "missing_info": [], "risks": []}),
            ),
            "agent_03_architecture":  lambda s: (
                setattr(s, "hld_document",    "# HLD [DRY-RUN stub]"),
                setattr(s, "lld_document",    "# LLD [DRY-RUN stub]"),
                setattr(s, "schema_document", "-- Schema [DRY-RUN stub]"),
                setattr(s, "openapi_spec",    "openapi: 3.0.0\ninfo:\n  title: stub"),
            ),
            "agent_04_security":      lambda s: setattr(s, "security_report", {
                "overall_risk_level": "low", "security_requirements": [], "owasp_risks": [],
                "threat_model": {}, "compliance_checks": {}, "secure_coding_guidelines": [],
            }),
            "agent_05_codegen":       lambda s: setattr(s, "generated_code", {
                "main.py": "# [DRY-RUN] Generated code stub\nprint('hello world')"
            }),
            "agent_12_frontend":      lambda s: setattr(s, "frontend_code", {
                "src/App.tsx": "// [DRY-RUN] Frontend stub"
            }),
            "agent_06_documentation": lambda s: setattr(s, "documentation", {
                "readme": "# README [DRY-RUN stub]"
            }),
            "agent_07_qa":            lambda s: setattr(s, "test_suite", {
                "test_plan": "# Test Plan [DRY-RUN stub]", "unit_tests": {}
            }),
            "agent_08_review":        lambda s: setattr(s, "review_report", {
                "overall_score": 85, "gate_passed": True,
                "summary": "[DRY-RUN] Code review stub", "issues": [],
            }),
            "agent_09_deployment":    lambda s: setattr(s, "deployment_config", {
                "provider": s.cloud_provider, "iac_files": {}, "cicd_files": {}, "k8s_manifests": {},
            }),
            "agent_10_monitoring":    lambda s: setattr(s, "monitoring_config", {
                "sla_targets": {"availability": "99.9%", "p99_latency_ms": 500}
            }),
            "agent_11_support":       lambda s: setattr(s, "support_log", [
                {"support_runbook": "[DRY-RUN] Support stub"}
            ]),
            "agent_13_packaging":     lambda s: setattr(s, "package_manifest", {
                "artifact": "[DRY-RUN] package stub", "format": "zip"
            }),
        }

        stub_fn = stubs.get(agent.agent_id)
        if stub_fn:
            stub_fn(state)

        return state

    # ── Cancel ────────────────────────────────────────────────────────────────
    def cancel(self) -> None:
        """Signal the running pipeline to stop after the current agent."""
        self.cancel_event.set()
        logger.warning("Pipeline cancellation requested")
