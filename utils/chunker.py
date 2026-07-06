"""
Text chunker — splits large documents into token-safe pieces for Claude.
Rough rule: 1 token ≈ 4 characters for English text.
claude-sonnet-4 context window: 200k tokens → ~800k chars.
We keep individual messages well under 40k tokens (~160k chars) to leave
room for the system prompt and the response.
"""

from __future__ import annotations

MAX_CHARS = 120_000   # ~30k tokens — safe single-message limit


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text into chunks no larger than max_chars, breaking on newlines."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            chunks.append(text[start:])
            break
        # Back up to nearest newline so we don't cut mid-sentence
        cut = text.rfind("\n", start, end)
        if cut == -1 or cut <= start:
            cut = end  # no newline found, hard cut
        chunks.append(text[start:cut])
        start = cut + 1

    return chunks


def truncate(text: str, max_chars: int = MAX_CHARS, label: str = "") -> str:
    """Return text truncated to max_chars with a note if truncated."""
    if len(text) <= max_chars:
        return text
    note = f"\n\n[...{label} truncated at {max_chars} chars for token safety...]"
    return text[: max_chars - len(note)] + note


def summarise_files(files: dict[str, str], max_chars_each: int = 800, max_files: int = 15) -> str:
    """Return a compact summary of generated code files for use in downstream prompts."""
    lines = []
    for path, content in list(files.items())[:max_files]:
        preview = content[:max_chars_each].replace("\n", " ")
        lines.append(f"• {path} ({len(content)} chars)\n  {preview}…")
    if len(files) > max_files:
        lines.append(f"  … and {len(files) - max_files} more files")
    return "\n".join(lines)
