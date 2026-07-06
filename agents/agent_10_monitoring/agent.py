"""Agent 10 — Monitoring & Observability Agent"""
from __future__ import annotations
import json
from pathlib import Path
from agents.base_agent import BaseAgent
from models.pipeline_state import PipelineState
from utils.file_utils import save_text, save_json, outputs_path, timestamped_name
from utils.chunker import truncate

FILE_FORMAT = """
Return ONLY files in this exact format:

=== FILE: path/to/file.yml ===
<full file content>
=== FILE: another/file.json ===
<full file content>

No JSON wrapper, no markdown fences, no explanation outside file blocks.
"""

PROMETHEUS_SYSTEM = """
You are the Monitoring & Observability Agent. Generate Prometheus & Grafana configuration.

Files to generate:
- config/prometheus/prometheus.yml              (scrape configs, job definitions for FastAPI app)
- config/prometheus/alerts/app_alerts.yml       (alert rules: high error rate, high latency p99, service down, CPU/memory, DB pool exhaustion, disk usage)
- config/grafana/provisioning/datasources/prometheus.yml
- config/grafana/dashboards/app_overview.json   (complete Grafana dashboard JSON with panels for: RPS, latency p50/p95/p99, error rate, active users, DB connections, cache hit rate)
- config/otel/otel-collector.yaml               (OpenTelemetry collector: receive OTLP, export to Prometheus + stdout)
- config/logging/app_logging.yaml               (structured JSON logging config)
""" + FILE_FORMAT

RUNBOOKS_SYSTEM = """
You are the Monitoring & Observability Agent. Generate operations runbooks.

Files to generate:
- monitoring/runbooks/high_error_rate.md    (symptoms, immediate actions, investigation, escalation, resolution)
- monitoring/runbooks/high_latency.md
- monitoring/runbooks/service_down.md
- monitoring/runbooks/database_issues.md
- monitoring/runbooks/memory_leak.md
""" + FILE_FORMAT

DOCS_SYSTEM = """
You are the Monitoring & Observability Agent. Generate monitoring documentation.

Files to generate:
- docs/INSTRUMENTATION_GUIDE.md   (how to add metrics, logs, traces to FastAPI Python code with examples)
- docs/ON_CALL_SCHEDULE.md        (on-call rotation template, escalation matrix, SLA definitions table)
""" + FILE_FORMAT

SLA_SYSTEM = """
You are the Monitoring & Observability Agent. Return a JSON object with SLA and health check definitions:

{
  "sla_definitions": {
    "availability_target": "99.9%",
    "p50_latency_ms": 100,
    "p95_latency_ms": 300,
    "p99_latency_ms": 500,
    "error_rate_threshold_pct": 0.1,
    "rpo_minutes": 60,
    "rto_minutes": 30
  },
  "health_checks": [
    {"name":"...","path":"/health/...","method":"GET","expected_status":200,"check_interval_seconds":30,"failure_threshold":3,"description":"..."}
  ]
}

Return ONLY the JSON object. No fences.
"""


class MonitoringAgent(BaseAgent):
    agent_id    = "agent_10_monitoring"
    name        = "Monitoring & Observability Agent"
    model_tier        = "haiku"
    max_output_tokens = 3072
    description = "Prometheus, Grafana, alerting rules, runbooks, OTel tracing, SLA definitions"

    def run(self, state: PipelineState) -> PipelineState:
        req    = state.requirements_json  or {}
        deploy = state.deployment_config  or {}

        tech_stack: dict = {}
        try:
            ts_files = sorted(Path(str(outputs_path("architecture", ""))).glob("tech_stack_*.json"))
            if ts_files:
                tech_stack = json.loads(ts_files[-1].read_text())
        except Exception:
            pass

        self.log("Generating monitoring and observability configuration (4 calls)")

        nfr_targets = [
            r for r in req.get("non_functional_requirements", [])
            if r.get("category") in ("performance", "availability", "reliability")
        ]

        ctx = f"""
Project: {state.project_name}
Cloud: {state.cloud_provider.upper()}

--- NFR TARGETS ---
{json.dumps(nfr_targets, indent=2)}

--- DEPLOYMENT ENVIRONMENTS ---
{json.dumps(deploy.get("environments", {}), indent=2)}

--- TECH STACK ---
{json.dumps(tech_stack, indent=2)}
"""

        all_files: dict[str, str] = {}
        base = outputs_path("deployments", "monitoring")

        # Call 1: Prometheus + Grafana + OTel
        self.log("Generating Prometheus/Grafana/OTel config (1/4)")
        all_files.update(self._generate_delimited_files(PROMETHEUS_SYSTEM, ctx))

        # Call 2: Runbooks
        self.log("Generating operations runbooks (2/4)")
        all_files.update(self._generate_delimited_files(RUNBOOKS_SYSTEM, ctx))

        # Call 3: Docs
        self.log("Generating monitoring docs (3/4)")
        all_files.update(self._generate_delimited_files(DOCS_SYSTEM, ctx))

        # Call 4: SLA + health checks JSON (small — safe to keep as JSON)
        self.log("Generating SLA & health check definitions (4/4)")
        from utils.json_parser import extract_json_with_retry
        sla_result = extract_json_with_retry(self._claude, SLA_SYSTEM, ctx, fallback={})

        state.monitoring_config = {
            "sla_definitions": sla_result.get("sla_definitions", {}),
            "health_checks":   sla_result.get("health_checks", []),
            "files":           list(all_files.keys()),
        }

        # Write all files
        written = 0
        for rel_path, content in all_files.items():
            try:
                fp = base / rel_path if not rel_path.startswith("docs/") else outputs_path("", rel_path)
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                written += 1
            except Exception as exc:
                self.log(f"Warning: could not write {rel_path}: {exc}")

        save_json(sla_result, "deployments/monitoring", timestamped_name("sla_definitions", "json"))

        sla  = sla_result.get("sla_definitions", {})
        hcs  = len(sla_result.get("health_checks", []))
        rbs  = sum(1 for k in all_files if "runbooks" in k)

        self.last_summary     = (
            f"{written} config files | {rbs} runbooks | {hcs} health checks | "
            f"SLA: {sla.get('availability_target','?')} availability, "
            f"p99<{sla.get('p99_latency_ms','?')}ms"
        )
        self.last_output_path = str(base)
        self.log(self.last_summary)
        return state
