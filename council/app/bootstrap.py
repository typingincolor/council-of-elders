from __future__ import annotations

from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.elders.openrouter import OpenRouterAdapter
from council.app.config import AppConfig
from council.domain.models import ElderId
from council.domain.ports import ElderPort

# The `gemini` slot defaults to an open-weights Llama model rather than
# a Gemini-family model deliberately: a same-lineage trio (all three of
# Anthropic, Google, OpenAI) produces R1 answers that overlap more than
# a mixed-lineage trio does, and the debate protocol only beats picking
# the best R1 when the roster has genuine architectural diversity. See
# `docs/experiments/2026-04-19-9288-homogenisation.md`. The slot label
# is just a label — the debate protocol is slot-keyed, not model-keyed.
_DEFAULT_OPENROUTER_MODELS: dict[ElderId, str] = {
    "claude": "anthropic/claude-sonnet-4.5",
    "gemini": "meta-llama/llama-3.1-70b-instruct",
    "chatgpt": "openai/gpt-5",
}


def build_elders(
    config: AppConfig,
    *,
    cli_models: dict[ElderId, str | None],
) -> tuple[dict[ElderId, ElderPort], bool]:
    if config.openrouter_api_key:
        elders: dict[ElderId, ElderPort] = {}
        for eid in ("claude", "gemini", "chatgpt"):
            model = (
                cli_models.get(eid)
                or config.openrouter_models.get(eid)
                or _DEFAULT_OPENROUTER_MODELS[eid]
            )
            elders[eid] = OpenRouterAdapter(
                elder_id=eid,
                model=model,
                api_key=config.openrouter_api_key,
            )
        return elders, True

    elders = {
        "claude": ClaudeCodeAdapter(model=cli_models.get("claude")),
        "gemini": GeminiCLIAdapter(model=cli_models.get("gemini")),
        "chatgpt": CodexCLIAdapter(model=cli_models.get("chatgpt")),
    }
    return elders, False
