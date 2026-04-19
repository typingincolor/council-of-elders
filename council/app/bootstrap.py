from __future__ import annotations

from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.app.config import AppConfig
from council.domain.models import ElderId
from council.domain.ports import ElderPort

_DEFAULT_OPENROUTER_MODELS: dict[ElderId, str] = {
    "claude": "anthropic/claude-sonnet-4.5",
    "gemini": "google/gemini-2.5-pro",
    "chatgpt": "openai/gpt-5",
}


def build_elders(
    config: AppConfig,
    *,
    cli_models: dict[ElderId, str | None],
) -> tuple[dict[ElderId, ElderPort], bool]:
    if config.openrouter_api_key:
        raise NotImplementedError  # filled in the next task

    elders: dict[ElderId, ElderPort] = {
        "claude": ClaudeCodeAdapter(model=cli_models.get("claude")),
        "gemini": GeminiCLIAdapter(model=cli_models.get("gemini")),
        "chatgpt": CodexCLIAdapter(model=cli_models.get("chatgpt")),
    }
    return elders, False
