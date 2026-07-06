"""
EventBus
─────────
Async pub/sub event bus used by the orchestrator to broadcast
pipeline progress in real-time. Both the FastAPI SSE endpoint
and the Streamlit UI subscribe to it.

Event schema:
  {
    "type":       "agent_started" | "agent_completed" | "agent_failed"
                  | "pipeline_started" | "pipeline_completed" | "pipeline_cancelled"
                  | "log",
    "run_id":     str,
    "timestamp":  ISO-8601 str,
    "agent_id":   str   (agent events only),
    "agent_name": str   (agent events only),
    "step":       int   (1-based agent position),
    "total":      int   (total number of agents),
    "summary":    str   (agent_completed only),
    "output_path":str   (agent_completed only),
    "error":      str   (agent_failed only),
    "message":    str   (log events only),
    "level":      str   (log events: INFO | WARNING | ERROR),
  }
"""

from __future__ import annotations
import queue
from datetime import datetime, timezone
from typing import Any
from loguru import logger


class EventBus:
    """
    Single shared in-process event bus.
    Subscribers receive events via thread-safe queue.Queue so they work
    both in Streamlit (no running event loop) and FastAPI async contexts.
    """

    def __init__(self) -> None:
        # run_id → list of subscriber queues
        self._subscribers: dict[str, list[queue.Queue]] = {}

    # ── Subscribe / Unsubscribe ────────────────────────────────────────────────
    def subscribe(self, run_id: str) -> queue.Queue:
        """Return a new Queue that will receive all events for this run."""
        q: queue.Queue = queue.Queue(maxsize=500)
        self._subscribers.setdefault(run_id, []).append(q)
        logger.debug(f"EventBus: subscriber added for run {run_id} (total={len(self._subscribers[run_id])})")
        return q

    def unsubscribe(self, run_id: str, q: queue.Queue) -> None:
        subs = self._subscribers.get(run_id, [])
        if q in subs:
            subs.remove(q)
        if not subs:
            self._subscribers.pop(run_id, None)
        logger.debug(f"EventBus: subscriber removed for run {run_id}")

    # ── Publish ────────────────────────────────────────────────────────────────
    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """Broadcast event to all subscribers for this run_id."""
        event.setdefault("run_id", run_id)
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        for q in list(self._subscribers.get(run_id, [])):
            try:
                q.put_nowait(event)
            except queue.Full:
                logger.warning(f"EventBus: queue full for run {run_id}, dropping event")

    # ── Convenience builders ───────────────────────────────────────────────────
    def pipeline_started(self, run_id: str, project_name: str, total_agents: int) -> None:
        self.publish(run_id, {
            "type":         "pipeline_started",
            "project_name": project_name,
            "total":        total_agents,
        })

    def agent_started(self, run_id: str, agent_id: str, agent_name: str, step: int, total: int) -> None:
        self.publish(run_id, {
            "type":       "agent_started",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "step":       step,
            "total":      total,
        })

    def agent_completed(self, run_id: str, agent_id: str, agent_name: str,
                        step: int, total: int, summary: str, output_path: str | None) -> None:
        self.publish(run_id, {
            "type":        "agent_completed",
            "agent_id":    agent_id,
            "agent_name":  agent_name,
            "step":        step,
            "total":       total,
            "summary":     summary,
            "output_path": output_path,
        })

    def agent_failed(self, run_id: str, agent_id: str, agent_name: str,
                     step: int, total: int, error: str) -> None:
        self.publish(run_id, {
            "type":       "agent_failed",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "step":       step,
            "total":      total,
            "error":      error,
        })

    def pipeline_completed(self, run_id: str, total_agents: int) -> None:
        self.publish(run_id, {
            "type":  "pipeline_completed",
            "total": total_agents,
        })

    def pipeline_cancelled(self, run_id: str, reason: str = "") -> None:
        self.publish(run_id, {"type": "pipeline_cancelled", "reason": reason})

    def log(self, run_id: str, message: str, level: str = "INFO") -> None:
        self.publish(run_id, {"type": "log", "message": message, "level": level})

    # ── Sentinel ───────────────────────────────────────────────────────────────
    def send_done(self, run_id: str) -> None:
        """Signal to all subscribers that the stream is finished."""
        self.publish(run_id, {"type": "__done__"})
        self._subscribers.pop(run_id, None)


# Global singleton — import this everywhere
event_bus = EventBus()
