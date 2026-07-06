"""
FastAPI backend for the SDLC Agent Pipeline.

Endpoints
─────────
POST   /pipeline/start                — upload files, kick off full pipeline
POST   /pipeline/start-dry-run        — same but dry_run=True (no Claude calls)
GET    /pipeline/{run_id}             — get current pipeline state
GET    /pipeline/{run_id}/stream      — SSE stream of live events
POST   /pipeline/{run_id}/resume      — resume a failed run from last checkpoint
POST   /pipeline/{run_id}/cancel      — cancel a running pipeline
DELETE /pipeline/{run_id}             — delete run record
GET    /pipeline                      — list all runs
GET    /agents                        — list all 11 agents
POST   /agents/{agent_id}/run         — run a single agent on an existing state
GET    /health                        — health check
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger

from config.logging import setup_logging
from config.settings import settings
from database.db import init_db
from models.pipeline_state import PipelineState
from orchestrator.events import event_bus
from orchestrator.pipeline import PipelineOrchestrator, AGENT_SEQUENCE
from orchestrator.router import list_agents, get_agent
from orchestrator.state_manager import PipelineStateManager

setup_logging()

app = FastAPI(
    title="SDLC Agent Pipeline API",
    description="Multi-agent SDLC pipeline powered by Claude",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory run registry: run_id → (state, orchestrator, task) ──────────────
_runs: dict[str, PipelineState] = {}
_orchestrators: dict[str, PipelineOrchestrator] = {}
_tasks: dict[str, asyncio.Task] = {}
_state_mgr = PipelineStateManager()


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    init_db()
    logger.info("SDLC Pipeline API started")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": "2.0.0"}


# ── Agents ────────────────────────────────────────────────────────────────────
@app.get("/agents")
def get_agents_list() -> dict:
    return {"agents": list_agents()}


# ── Pipeline — start ──────────────────────────────────────────────────────────
@app.post("/pipeline/start")
async def start_pipeline(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    cloud_provider: str = Form("aws"),
    start_from: int = Form(0),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Upload requirement files and start the full pipeline."""
    run_id    = str(uuid.uuid4())
    saved     = _save_uploads(run_id, files)
    state     = PipelineState(
        run_id=run_id,
        project_name=project_name,
        cloud_provider=cloud_provider,
        input_files=saved,
    )
    _runs[run_id] = state
    background_tasks.add_task(_execute_pipeline, run_id, state, start_from, False)
    return {"run_id": run_id, "status": "started", "files_uploaded": len(saved)}


@app.post("/pipeline/start-dry-run")
async def start_dry_run(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    cloud_provider: str = Form("aws"),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Start pipeline in dry-run mode (no Claude API calls)."""
    run_id = str(uuid.uuid4())
    saved  = _save_uploads(run_id, files)
    state  = PipelineState(
        run_id=run_id,
        project_name=project_name,
        cloud_provider=cloud_provider,
        input_files=saved,
    )
    _runs[run_id] = state
    background_tasks.add_task(_execute_pipeline, run_id, state, 0, True)
    return {"run_id": run_id, "status": "started (dry-run)", "files_uploaded": len(saved)}


# ── Pipeline — inspect ────────────────────────────────────────────────────────
@app.get("/pipeline")
def list_runs() -> dict:
    return {"runs": _state_mgr.list_runs()}


@app.get("/pipeline/{run_id}")
def get_pipeline_run(run_id: str) -> dict:
    # Check in-memory first, then DB
    state = _runs.get(run_id) or _state_mgr.load_run(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return state.model_dump(mode="json")


# ── Pipeline — control ────────────────────────────────────────────────────────
@app.post("/pipeline/{run_id}/resume")
async def resume_pipeline(run_id: str, background_tasks: BackgroundTasks) -> dict:
    """Resume a failed or incomplete pipeline from the last successful checkpoint."""
    state = _runs.get(run_id) or _state_mgr.load_run(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    resume_from = _state_mgr.get_resume_index(state)
    if resume_from >= len(AGENT_SEQUENCE):
        return {"message": "Pipeline already complete — nothing to resume", "run_id": run_id}

    last_ok = _state_mgr.get_last_successful_agent(state)
    _runs[run_id] = state
    background_tasks.add_task(_execute_pipeline, run_id, state, resume_from, False)
    return {
        "run_id": run_id,
        "status": "resuming",
        "resume_from_step": resume_from + 1,
        "last_successful_agent": last_ok,
    }


@app.post("/pipeline/{run_id}/cancel")
def cancel_pipeline(run_id: str) -> dict:
    orch = _orchestrators.get(run_id)
    if not orch:
        raise HTTPException(status_code=404, detail=f"No active orchestrator for run {run_id}")
    orch.cancel()
    return {"run_id": run_id, "status": "cancel_requested"}


@app.delete("/pipeline/{run_id}")
def delete_run(run_id: str) -> dict:
    _runs.pop(run_id, None)
    _orchestrators.pop(run_id, None)
    task = _tasks.pop(run_id, None)
    if task and not task.done():
        task.cancel()
    return {"run_id": run_id, "status": "deleted"}


# ── Pipeline — SSE stream ─────────────────────────────────────────────────────
@app.get("/pipeline/{run_id}/stream")
async def stream_pipeline_events(run_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream.
    Subscribe before the run starts, or late-join an in-progress run.
    Sends JSON event objects; terminates with a __done__ sentinel.
    """
    if run_id not in _runs and not _state_mgr.load_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    queue = event_bus.subscribe(run_id)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield ": ping\n\n"
                    continue

                if event.get("type") == "__done__":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break

                yield f"data: {json.dumps(event)}\n\n"
        finally:
            event_bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Single agent run ──────────────────────────────────────────────────────────
@app.post("/agents/{agent_id}/run")
async def run_single_agent(agent_id: str, run_id: str) -> dict:
    """Run one specific agent against an existing pipeline state."""
    state = _runs.get(run_id) or _state_mgr.load_run(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    agent = get_agent(agent_id)
    try:
        if asyncio.iscoroutinefunction(agent.run):
            updated_state = await agent.run(state)
        else:
            updated_state = await asyncio.to_thread(agent.run, state)

        _runs[run_id] = updated_state
        _state_mgr.save_run(updated_state)
        return {"agent_id": agent_id, "summary": agent.last_summary, "output_path": agent.last_output_path}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Private helpers ───────────────────────────────────────────────────────────
def _save_uploads(run_id: str, files: list[UploadFile]) -> list[str]:
    upload_dir = Path(settings.outputs_dir) / "uploads" / run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        dest = upload_dir / f.filename
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(str(dest))
    return saved


async def _execute_pipeline(
    run_id: str,
    state: PipelineState,
    start_from: int,
    dry_run: bool,
) -> None:
    """Background task: create orchestrator, run pipeline, update in-memory store."""
    orch = PipelineOrchestrator()
    _orchestrators[run_id] = orch

    try:
        final_state = await orch.run(state, start_from=start_from, dry_run=dry_run)
        _runs[run_id] = final_state
    except Exception as exc:
        logger.error(f"Pipeline execution error for run {run_id}: {exc}")
        event_bus.log(run_id, f"Fatal pipeline error: {exc}", level="ERROR")
        event_bus.send_done(run_id)
    finally:
        _orchestrators.pop(run_id, None)
