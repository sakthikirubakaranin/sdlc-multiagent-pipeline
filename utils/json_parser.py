"""
Robust JSON extraction from Claude responses.

Claude sometimes wraps JSON in markdown code fences, adds explanation text
before/after, or returns slightly malformed JSON. This module handles all
those cases and retries with a repair prompt when needed.
"""

from __future__ import annotations
import json
import re
from typing import Any, Optional
from loguru import logger


def extract_json(text: str) -> Optional[Any]:
    """
    Try multiple strategies to extract valid JSON from a Claude response.

    Strategies (in order):
      1. Direct parse (Claude returned clean JSON)
      2. Strip markdown code fences  ```json ... ```
      3. Find the first { ... } or [ ... ] block
      4. Give up → return None
    """
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: find outermost { } object
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 4: find outermost [ ] array
    bracket_match = re.search(r"\[[\s\S]*\]", text)
    if bracket_match:
        try:
            return json.loads(bracket_match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("extract_json: all strategies failed, returning None")
    return None


def extract_json_with_retry(
    claude_client,
    system_prompt: str,
    user_message: str,
    fallback: Any = None,
    max_attempts: int = 3,
) -> Any:
    """
    Call Claude and extract JSON.  If parsing fails, re-ask Claude to return
    only the JSON.  Returns `fallback` if all attempts fail.
    """
    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            response = claude_client.chat(
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        else:
            # Repair prompt: ask Claude to fix its own output
            repair_msg = (
                "Your previous response could not be parsed as JSON.\n"
                "Please return ONLY a valid JSON object or array — "
                "no markdown, no explanation, no code fences.\n\n"
                f"Original request:\n{user_message[:500]}"
            )
            response = claude_client.chat(
                system="You are a JSON formatting assistant. Return only valid JSON.",
                messages=[{"role": "user", "content": repair_msg}],
            )

        result = extract_json(response)
        if result is not None:
            if attempt > 1:
                logger.info(f"JSON extracted on attempt {attempt}")
            return result

        logger.warning(f"JSON parse failed on attempt {attempt}/{max_attempts}")

    logger.error("extract_json_with_retry: all attempts failed, returning fallback")
    return fallback
