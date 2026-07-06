"""
SQLAlchemy ORM table definitions.
"""

from sqlalchemy import Column, String, Text, DateTime, JSON, Enum as SAEnum
from sqlalchemy.sql import func
from database.db import Base
from models.pipeline_state import AgentStatus


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    run_id       = Column(String(36), primary_key=True)
    project_name = Column(String(256), nullable=False)
    cloud_provider = Column(String(16), default="aws")
    state_json   = Column(JSON, nullable=True)          # Full PipelineState snapshot
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentRunLog(Base):
    __tablename__ = "agent_run_logs"

    id           = Column(String(36), primary_key=True)
    run_id       = Column(String(36), nullable=False, index=True)
    agent_id     = Column(String(64), nullable=False)
    agent_name   = Column(String(128), nullable=False)
    status       = Column(SAEnum(AgentStatus), default=AgentStatus.PENDING)
    summary      = Column(Text, nullable=True)
    error        = Column(Text, nullable=True)
    output_path  = Column(String(512), nullable=True)
    started_at   = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
