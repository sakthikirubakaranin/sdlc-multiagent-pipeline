"""
PipelineStateManager
─────────────────────
Persists PipelineState to the database after every agent completes.
Enables:
  • Resume a failed/interrupted run from the last successful agent
  • List all historical runs
  • Load any past run's full state
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.schemas import PipelineRun, AgentRunLog
from models.pipeline_state import PipelineState, AgentResult, AgentStatus


class PipelineStateManager:

    # ── Persist ────────────────────────────────────────────────────────────────
    @staticmethod
    def save_run(state: PipelineState) -> None:
        """Upsert the full pipeline state snapshot to the DB."""
        db: Session = SessionLocal()
        try:
            existing = db.query(PipelineRun).filter_by(run_id=state.run_id).first()
            state_dict = state.model_dump(mode="json")

            if existing:
                existing.state_json   = state_dict
                existing.updated_at   = datetime.utcnow()
            else:
                db.add(PipelineRun(
                    run_id=state.run_id,
                    project_name=state.project_name,
                    cloud_provider=state.cloud_provider,
                    state_json=state_dict,
                ))
            db.commit()
            logger.debug(f"State saved | run_id={state.run_id}")
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to save state: {exc}")
        finally:
            db.close()

    @staticmethod
    def save_agent_result(run_id: str, result: AgentResult) -> None:
        """Upsert a single agent's result log row."""
        db: Session = SessionLocal()
        try:
            existing = (
                db.query(AgentRunLog)
                .filter_by(run_id=run_id, agent_id=result.agent_id)
                .first()
            )
            if existing:
                existing.status       = result.status
                existing.summary      = result.summary
                existing.error        = result.error
                existing.output_path  = result.output_path
                existing.started_at   = result.started_at
                existing.completed_at = result.completed_at
            else:
                db.add(AgentRunLog(
                    id           = str(uuid.uuid4()),
                    run_id       = run_id,
                    agent_id     = result.agent_id,
                    agent_name   = result.agent_name,
                    status       = result.status,
                    summary      = result.summary,
                    error        = result.error,
                    output_path  = result.output_path,
                    started_at   = result.started_at,
                    completed_at = result.completed_at,
                ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to save agent result: {exc}")
        finally:
            db.close()

    # ── Load ───────────────────────────────────────────────────────────────────
    @staticmethod
    def load_last_run_for_project(project_name: str) -> Optional[PipelineState]:
        """
        Load the most useful saved run for a project — the one with the most
        completed agents (i.e. the furthest-along run), so resume picks up where
        real work actually finished, not an empty retry run.
        """
        db: Session = SessionLocal()
        try:
            rows = (
                db.query(PipelineRun)
                .filter_by(project_name=project_name)
                .order_by(PipelineRun.updated_at.desc())
                .limit(20)
                .all()
            )
            best_state: Optional[PipelineState] = None
            best_count = -1
            for row in rows:
                if not row.state_json:
                    continue
                try:
                    candidate = PipelineState.model_validate(row.state_json)
                except Exception:
                    continue
                # Count completed agents — pick the run that got furthest
                results = candidate.agent_results
                if isinstance(results, dict):
                    results = list(results.values())
                completed = sum(1 for r in (results or []) if r.status == AgentStatus.COMPLETED)
                if completed > best_count:
                    best_count = completed
                    best_state = candidate
            if best_state:
                logger.info(f"Resuming best run: {best_state.run_id} ({best_count} agents completed)")
            return best_state
        except Exception as exc:
            logger.error(f"Failed to load last run for project '{project_name}': {exc}")
            return None
        finally:
            db.close()

    @staticmethod
    def load_run(run_id: str) -> Optional[PipelineState]:
        """Load a full PipelineState from the DB by run_id."""
        db: Session = SessionLocal()
        try:
            row = db.query(PipelineRun).filter_by(run_id=run_id).first()
            if not row or not row.state_json:
                return None
            return PipelineState.model_validate(row.state_json)
        except Exception as exc:
            logger.error(f"Failed to load run {run_id}: {exc}")
            return None
        finally:
            db.close()

    @staticmethod
    def list_runs(limit: int = 50) -> list[dict]:
        """Return a summary list of all pipeline runs."""
        db: Session = SessionLocal()
        try:
            rows = (
                db.query(PipelineRun)
                .order_by(PipelineRun.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "run_id":       r.run_id,
                    "project_name": r.project_name,
                    "cloud_provider": r.cloud_provider,
                    "created_at":   r.created_at.isoformat() if r.created_at else None,
                    "updated_at":   r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error(f"Failed to list runs: {exc}")
            return []
        finally:
            db.close()

    # ── Resume helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def get_resume_index(state: PipelineState) -> int:
        """
        Return the index (0-based) of the next agent to run.
        If all completed → returns len(AGENT_SEQUENCE) (no-op).
        If none ran → returns 0.
        """
        from orchestrator.pipeline import AGENT_SEQUENCE
        completed_ids = {
            r.agent_id
            for r in state.agent_results
            if r.status == AgentStatus.COMPLETED
        }
        for i, AgentCls in enumerate(AGENT_SEQUENCE):
            if AgentCls().agent_id not in completed_ids:
                return i
        return len(AGENT_SEQUENCE)

    @staticmethod
    def get_last_successful_agent(state: PipelineState) -> Optional[str]:
        completed = [
            r for r in state.agent_results
            if r.status == AgentStatus.COMPLETED
        ]
        if not completed:
            return None
        return sorted(completed, key=lambda r: r.completed_at or datetime.min)[-1].agent_name
