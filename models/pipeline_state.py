"""
Canonical data models for the pipeline state passed between agents.
Every agent reads from and writes to a PipelineState instance.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum
import uuid


class AgentStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class AgentResult(BaseModel):
    agent_id: str
    agent_name: str
    status: AgentStatus = AgentStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_path: Optional[str] = None    # Path to the primary artifact
    summary: Optional[str] = None        # Short human-readable summary
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineState(BaseModel):
    """
    Single shared state object that flows through all 11 agents.
    Each agent appends its results to `agent_results`.
    """
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str = "untitled_project"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # ── Inputs ───────────────────────────────────────────────────────────────
    input_files: list[str] = Field(default_factory=list)   # Uploaded file paths
    raw_text: str = ""                                      # Aggregated extracted text

    # ── Agent Outputs (populated progressively) ───────────────────────────────
    requirements_json: Optional[dict] = None       # Agent 1 output
    prd_document: Optional[str] = None             # Agent 2 output (markdown)
    gap_analysis: Optional[dict] = None            # Agent 2 output
    hld_document: Optional[str] = None             # Agent 3 output
    lld_document: Optional[str] = None             # Agent 3 output
    schema_document: Optional[str] = None          # Agent 3 output (SQL/ERD)
    openapi_spec: Optional[str] = None             # Agent 3 output (YAML)
    security_report: Optional[dict] = None         # Agent 4 output
    generated_code: Optional[dict] = None          # Agent 5 output {filepath: content}
    documentation: Optional[dict] = None           # Agent 6 output
    test_suite: Optional[dict] = None              # Agent 7 output
    review_report: Optional[dict] = None           # Agent 8 output
    deployment_config: Optional[dict] = None       # Agent 9 output
    frontend_code: Optional[dict] = None           # Agent 12 output (moved to pos 6)
    monitoring_config: Optional[dict] = None       # Agent 10 output
    support_log: Optional[list] = None             # Agent 11 output
    package_manifest: Optional[dict] = None        # Agent 13 output

    # ── Tracking ─────────────────────────────────────────────────────────────
    agent_results: list[AgentResult] = Field(default_factory=list)
    current_agent: Optional[str] = None
    cloud_provider: str = "aws"

    def get_agent_result(self, agent_id: str) -> Optional[AgentResult]:
        return next((r for r in self.agent_results if r.agent_id == agent_id), None)

    def update_agent(self, result: AgentResult) -> None:
        existing = self.get_agent_result(result.agent_id)
        if existing:
            idx = self.agent_results.index(existing)
            self.agent_results[idx] = result
        else:
            self.agent_results.append(result)
        self.updated_at = datetime.utcnow()
