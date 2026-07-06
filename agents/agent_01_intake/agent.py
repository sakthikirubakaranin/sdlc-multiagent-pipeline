"""
Agent 01 — Requirements Intake Agent
──────────────────────────────────────
Accepts multi-modal input files:
  • Text / Markdown / CSV
  • PDF  (pdfplumber)
  • DOCX (python-docx)
  • Audio (Whisper — local, free)
  • Video (moviepy → audio → Whisper)

Extracts all raw text, feeds it to Claude in chunks if needed,
and outputs a structured Requirements JSON.
"""

from __future__ import annotations

import os
from pathlib import Path
from loguru import logger

from agents.base_agent import BaseAgent
from agents.agent_01_intake.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from models.pipeline_state import PipelineState
from utils.file_utils import save_json, timestamped_name
from utils.json_parser import extract_json_with_retry
from utils.chunker import chunk_text, truncate


class IntakeAgent(BaseAgent):
    agent_id    = "agent_01_intake"
    name        = "Requirements Intake Agent"
    model_tier        = "haiku"
    max_output_tokens = 2048
    description = "Ingests video/audio/PDF/DOCX/TXT and extracts structured requirements via Claude"

    TEXT_EXTS  = {".txt", ".md", ".rst", ".csv"}
    PDF_EXTS   = {".pdf"}
    DOCX_EXTS  = {".docx", ".doc"}
    AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
    VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    # ── Main entry point ──────────────────────────────────────────────────────
    def run(self, state: PipelineState) -> PipelineState:
        self.log(f"Processing {len(state.input_files)} input file(s)")

        # ── Step 1: Extract raw text from every file ──────────────────────────
        parts: list[str] = []
        for filepath in state.input_files:
            text = self._extract_file(filepath)
            if text:
                parts.append(f"[Source: {Path(filepath).name}]\n{text}")

        if not parts:
            raise ValueError("No readable content found in the provided files.")

        raw_text = "\n\n---\n\n".join(parts)
        state.raw_text = raw_text
        total_chars = len(raw_text)
        self.log(f"Extracted {total_chars:,} characters from {len(parts)} file(s)")

        # ── Step 2: Send to Claude (chunk if too large) ───────────────────────
        chunks = chunk_text(raw_text)

        if len(chunks) == 1:
            requirements_json = self._analyse_chunk(raw_text, len(parts))
        else:
            self.log(f"Text split into {len(chunks)} chunks — analysing each, then merging")
            requirements_json = self._analyse_chunked(chunks, len(parts))

        if not requirements_json:
            raise ValueError("Claude did not return valid requirements JSON.")

        state.requirements_json = requirements_json

        # ── Step 3: Save artifact ─────────────────────────────────────────────
        filename = timestamped_name("requirements", "json")
        path = save_json(requirements_json, "requirements", filename)

        fr  = len(requirements_json.get("functional_requirements", []))
        nfr = len(requirements_json.get("non_functional_requirements", []))
        self.last_summary     = f"Extracted {fr} functional + {nfr} non-functional requirements from {len(parts)} file(s)"
        self.last_output_path = str(path)
        self.log(self.last_summary)
        return state

    # ── Claude analysis ───────────────────────────────────────────────────────
    def _analyse_chunk(self, text: str, file_count: int) -> dict | None:
        user_msg = USER_TEMPLATE.format(
            char_count=len(text),
            file_count=file_count,
            raw_text=text,
        )
        return extract_json_with_retry(
            self._claude,
            SYSTEM_PROMPT,
            user_msg,
            fallback=None,
        )

    def _analyse_chunked(self, chunks: list[str], file_count: int) -> dict:
        """Analyse each chunk separately, then merge the results."""
        merged: dict = {
            "project_name": "",
            "project_description": "",
            "stakeholders": [],
            "functional_requirements": [],
            "non_functional_requirements": [],
            "constraints": [],
            "assumptions": [],
            "out_of_scope": [],
            "tech_preferences": [],
            "integrations": [],
            "timeline_hints": [],
            "raw_notes": "",
        }

        fr_counter  = 1
        nfr_counter = 1

        for i, chunk in enumerate(chunks):
            self.log(f"Analysing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
            result = self._analyse_chunk(chunk, file_count)
            if not result:
                continue

            # Project info — use first non-empty value
            if not merged["project_name"] and result.get("project_name"):
                merged["project_name"] = result["project_name"]
            if not merged["project_description"] and result.get("project_description"):
                merged["project_description"] = result["project_description"]

            # Re-number FRs to avoid duplicates across chunks
            for fr in result.get("functional_requirements", []):
                fr["id"] = f"FR-{fr_counter:03d}"
                fr_counter += 1
                merged["functional_requirements"].append(fr)

            for nfr in result.get("non_functional_requirements", []):
                nfr["id"] = f"NFR-{nfr_counter:03d}"
                nfr_counter += 1
                merged["non_functional_requirements"].append(nfr)

            # Merge lists, deduplicating simple strings
            for key in ("stakeholders", "constraints", "assumptions",
                        "out_of_scope", "tech_preferences", "integrations", "timeline_hints"):
                for item in result.get(key, []):
                    if item not in merged[key]:
                        merged[key].append(item)

            if result.get("raw_notes"):
                merged["raw_notes"] += f"\n[Chunk {i+1}] {result['raw_notes']}"

        return merged

    # ── File extractors ───────────────────────────────────────────────────────
    def _extract_file(self, filepath: str) -> str:
        ext = Path(filepath).suffix.lower()
        try:
            if ext in self.TEXT_EXTS:
                return self._read_text(filepath)
            elif ext in self.PDF_EXTS:
                return self._extract_pdf(filepath)
            elif ext in self.DOCX_EXTS:
                return self._extract_docx(filepath)
            elif ext in self.AUDIO_EXTS:
                return self._transcribe_audio(filepath)
            elif ext in self.VIDEO_EXTS:
                return self._transcribe_video(filepath)
            else:
                self.log(f"Unsupported extension '{ext}' — skipping {Path(filepath).name}")
                return ""
        except Exception as exc:
            self.log(f"Failed to extract {Path(filepath).name}: {exc}")
            return ""

    def _read_text(self, filepath: str) -> str:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _extract_pdf(self, filepath: str) -> str:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber not installed — run: pip install pdfplumber")

        pages = []
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    pages.append(f"[Page {i+1}]\n{text}")
                # Also extract tables as text
                for table in (page.extract_tables() or []):
                    rows = [" | ".join(str(c or "") for c in row) for row in table]
                    pages.append("\n".join(rows))

        self.log(f"PDF: extracted {len(pages)} pages from {Path(filepath).name}")
        return "\n\n".join(pages)

    def _extract_docx(self, filepath: str) -> str:
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("python-docx not installed — run: pip install python-docx")

        doc = Document(filepath)
        parts = []

        # Paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                style = para.style.name if para.style else ""
                prefix = f"[{style}] " if "Heading" in style else ""
                parts.append(f"{prefix}{para.text.strip()}")

        # Tables
        for table in doc.tables:
            rows = []
            for row in table.rows:
                rows.append(" | ".join(cell.text.strip() for cell in row.cells))
            parts.append("\n".join(rows))

        self.log(f"DOCX: extracted {len(parts)} elements from {Path(filepath).name}")
        return "\n\n".join(parts)

    def _transcribe_audio(self, filepath: str) -> str:
        try:
            import whisper
        except ImportError:
            raise RuntimeError(
                "openai-whisper not installed — run: pip install openai-whisper\n"
                "(Note: also requires ffmpeg — install via brew install ffmpeg)"
            )
        from config.settings import settings
        self.log(f"Transcribing audio with Whisper ({settings.whisper_model}): {Path(filepath).name}")
        model = whisper.load_model(settings.whisper_model)
        result = model.transcribe(filepath, verbose=False)
        transcript = result["text"]
        self.log(f"Transcription complete: {len(transcript):,} chars")
        return transcript

    def _transcribe_video(self, filepath: str) -> str:
        import tempfile
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            raise RuntimeError("moviepy not installed — run: pip install moviepy")

        self.log(f"Extracting audio from video: {Path(filepath).name}")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name

        try:
            clip = VideoFileClip(filepath)
            clip.audio.write_audiofile(audio_path, verbose=False, logger=None)
            clip.close()
            return self._transcribe_audio(audio_path)
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
