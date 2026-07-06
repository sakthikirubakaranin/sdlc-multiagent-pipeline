"""
Singleton wrapper around the Anthropic Claude client.
All agents use this to call Claude — centralises retry logic,
token tracking, cost estimation, prompt caching, and model config.

Cost optimisations (v2):
  • Per-call model override  — cheap agents use Haiku (~25× less expensive)
  • Anthropic Prompt Caching — system prompts cached → 90 % off cached tokens
  • Per-call max_tokens cap  — stops over-generation
"""

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from typing import Optional
from config.settings import settings


# ── Model constants ────────────────────────────────────────────────────────────
SONNET = "claude-sonnet-4-6"       # powerful — complex generation
HAIKU  = "claude-haiku-4-5-20251001"   # cheap   — simple/structured tasks

# Cost per 1 M tokens (USD) — approximate, check console for actual rates
_COST_IN  = {SONNET: 3.00,  HAIKU: 0.25}
_COST_OUT = {SONNET: 15.00, HAIKU: 1.25}
_COST_CACHE_WRITE = {SONNET: 3.75, HAIKU: 0.30}   # writing to cache
_COST_CACHE_READ  = {SONNET: 0.30, HAIKU: 0.03}   # reading from cache (90 % off)


class ClaudeClient:
    _instance: Optional["ClaudeClient"] = None

    def __init__(self) -> None:
        self._client: Optional[anthropic.Anthropic] = None
        self.default_model = settings.anthropic_model
        self.default_max_tokens = settings.anthropic_max_tokens

        # Usage counters
        self._total_input_tokens        = 0
        self._total_output_tokens       = 0
        self._total_cache_write_tokens  = 0
        self._total_cache_read_tokens   = 0
        self._total_calls               = 0
        self._estimated_cost_usd        = 0.0

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    @classmethod
    def get(cls) -> "ClaudeClient":
        if cls._instance is None:
            cls._instance = ClaudeClient()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton and counters — called at the start of each pipeline run."""
        cls._instance = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type(anthropic.RateLimitError),
    )
    def chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
        model: Optional[str] = None,
        use_cache: bool = True,
    ) -> str:
        """
        Send a chat request to Claude and return the response text.

        Args:
            system:     System prompt (cached when use_cache=True).
            messages:   Conversation messages.
            max_tokens: Cap on output tokens (defaults to settings value).
            temperature: Sampling temperature.
            model:      Model override (SONNET or HAIKU). Defaults to settings model.
            use_cache:  Enable Anthropic prompt caching for the system prompt.
        """
        _model     = model or self.default_model
        _max_tok   = max_tokens or self.default_max_tokens
        self._total_calls += 1

        # ── Build system param (list format for cache_control) ─────────────────
        if use_cache:
            system_param = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            betas = ["prompt-caching-2024-07-31"]
        else:
            system_param = system
            betas = []

        # ── API call ───────────────────────────────────────────────────────────
        kwargs: dict = dict(
            model=_model,
            max_tokens=_max_tok,
            system=system_param,
            messages=messages,
            temperature=temperature,
        )
        if betas:
            response = self.client.beta.messages.create(betas=betas, **kwargs)
        else:
            response = self.client.messages.create(**kwargs)

        # ── Token accounting ───────────────────────────────────────────────────
        usage = response.usage
        in_tok  = getattr(usage, "input_tokens",              0)
        out_tok = getattr(usage, "output_tokens",             0)
        cw_tok  = getattr(usage, "cache_creation_input_tokens", 0)
        cr_tok  = getattr(usage, "cache_read_input_tokens",    0)

        self._total_input_tokens       += in_tok
        self._total_output_tokens      += out_tok
        self._total_cache_write_tokens += cw_tok
        self._total_cache_read_tokens  += cr_tok

        # Cost estimate
        def _cost(tok: int, rate: float) -> float:
            return tok / 1_000_000 * rate

        call_cost = (
            _cost(in_tok,  _COST_IN.get(_model,  3.0))
            + _cost(out_tok, _COST_OUT.get(_model, 15.0))
            + _cost(cw_tok,  _COST_CACHE_WRITE.get(_model, 3.75))
            + _cost(cr_tok,  _COST_CACHE_READ.get(_model,  0.30))
        )
        self._estimated_cost_usd += call_cost

        logger.debug(
            f"Claude [{_model.split('-')[1]}] | "
            f"in={in_tok} out={out_tok} cw={cw_tok} cr={cr_tok} | "
            f"call_cost=${call_cost:.4f} total=${self._estimated_cost_usd:.4f}"
        )

        return response.content[0].text

    def usage_summary(self) -> dict:
        saved_by_cache = self._total_cache_read_tokens
        return {
            "total_input_tokens":        self._total_input_tokens,
            "total_output_tokens":       self._total_output_tokens,
            "cache_write_tokens":        self._total_cache_write_tokens,
            "cache_read_tokens":         self._total_cache_read_tokens,
            "total_calls":               self._total_calls,
            "estimated_cost_usd":        round(self._estimated_cost_usd, 4),
            "estimated_savings_usd":     round(
                saved_by_cache / 1_000_000 * (3.00 - 0.30), 4  # Sonnet saving
            ),
        }


# Convenience singleton accessor
claude = ClaudeClient.get
