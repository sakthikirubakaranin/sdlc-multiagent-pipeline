"""
BaseAgent — all 12 SDLC agents inherit from this class.

Contract:
  • Each subclass sets agent_id, name, description
  • Each subclass sets model_tier ("haiku" | "sonnet") and max_output_tokens
  • Each subclass implements run(state) -> PipelineState
  • After run(), the agent sets self.last_summary and self.last_output_path

Cost-saving pattern:
  Simple/structured agents → model_tier = "haiku"  (~25x cheaper)
  Complex generation agents → model_tier = "sonnet"
  All system prompts are cached via Anthropic prompt-caching beta.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger
from utils.claude_client import ClaudeClient, SONNET, HAIKU
from models.pipeline_state import PipelineState


class BaseAgent(ABC):
    # ── Subclasses must define these ─────────────────────────────────────────
    agent_id:    str = "base"
    name:        str = "Base Agent"
    description: str = "Abstract base class"

    # ── Cost controls — override per agent ────────────────────────────────────
    # "haiku"  → claude-haiku (cheap, fast — for structured/simple tasks)
    # "sonnet" → claude-sonnet (powerful — for complex generation)
    model_tier:        str = "sonnet"
    max_output_tokens: int = 4096

    def __init__(self) -> None:
        self._claude_instance: Optional[ClaudeClient] = None
        self.last_summary:     Optional[str] = None
        self.last_output_path: Optional[str] = None

    @property
    def _claude(self) -> ClaudeClient:
        if self._claude_instance is None:
            self._claude_instance = ClaudeClient.get()
        return self._claude_instance

    @property
    def _model(self) -> str:
        return HAIKU if self.model_tier == "haiku" else SONNET

    # ── Core interface ────────────────────────────────────────────────────────
    @abstractmethod
    def run(self, state: PipelineState) -> PipelineState:
        """Execute the agent's task, mutate & return the state."""
        ...

    # ── Multi-file plain-text helper ─────────────────────────────────────────
    def _generate_delimited_files(
        self,
        system: str,
        user: str,
        delimiter: str = "=== FILE:",
    ) -> dict[str, str]:
        """
        Call Claude expecting a plain-text response in the format:

            === FILE: path/to/file.py ===
            <file content>
            === FILE: another/file.yaml ===
            <file content>

        Returns a dict of {relative_path: content}.
        Uses prompt caching on the system prompt automatically.
        """
        import re
        response = self._claude.chat(
            system=system,
            messages=[{"role": "user", "content": user}],
            model=self._model,
            max_tokens=self.max_output_tokens,
            use_cache=True,
        )
        pattern = rf"{re.escape(delimiter)}\s*(.+?)\s*===\n([\s\S]*?)(?={re.escape(delimiter)}|$)"
        matches = re.findall(pattern, response)
        files: dict[str, str] = {}
        for path, content in matches:
            path = path.strip()
            if path:
                files[path] = content.rstrip("\n")
        if not files:
            logger.warning(f"[{self.agent_id}] _generate_delimited_files: no files parsed")
        return files

    # ── Disk-recovery helper ──────────────────────────────────────────────────
    def _read_latest_output(self, subdir: str, pattern: str) -> str:
        """Read the most recently saved file matching pattern.

        Search order:
          1. outputs/{current_project}/{subdir}/   (exact project match)
          2. outputs/*/{subdir}/                   (any project — picks newest file)
          3. outputs/{subdir}/                     (legacy flat layout)
        """
        from utils.file_utils import outputs_path
        from config.settings import settings
        from pathlib import Path

        # 1. Current project folder
        try:
            files = sorted(Path(str(outputs_path(subdir, ""))).glob(pattern))
            if files:
                self.log(f"Recovered '{pattern}' from project folder: {files[-1].name}")
                return files[-1].read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[{self.agent_id}] disk-recovery (project): {exc}")

        # 2. Search ALL project subdirectories — pick newest matching file
        try:
            outputs_root = Path(settings.outputs_dir)
            all_matches = sorted(outputs_root.glob(f"*/{subdir}/{pattern}"))
            if all_matches:
                newest = all_matches[-1]
                self.log(f"Recovered '{pattern}' from '{newest.parent.parent.name}': {newest.name}")
                return newest.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[{self.agent_id}] disk-recovery (global): {exc}")

        # 3. Legacy flat layout (no project subdirectory)
        try:
            flat = Path(settings.outputs_dir) / subdir
            files = sorted(flat.glob(pattern))
            if files:
                self.log(f"Recovered '{pattern}' from flat layout: {files[-1].name}")
                return files[-1].read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[{self.agent_id}] disk-recovery (flat): {exc}")

        return ""

    # ── Shared helpers ────────────────────────────────────────────────────────
    def ask_claude(
        self,
        system: str,
        user_message: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
    ) -> str:
        _max = max_tokens or self.max_output_tokens
        logger.debug(f"[{self.agent_id}] → Claude/{self.model_tier} ({len(user_message)} chars, max={_max})")
        return self._claude.chat(
            system=system,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=_max,
            temperature=temperature,
            model=self._model,
            use_cache=True,
        )

    def log(self, message: str) -> None:
        logger.info(f"[{self.agent_id}] {message}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.agent_id} tier={self.model_tier}>"
