"""build_elders() decides between OpenRouter and subprocess adapters."""

from __future__ import annotations

from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.app.bootstrap import build_elders
from council.app.config import AppConfig


class TestSubprocessBranch:
    def test_no_key_builds_subprocess_adapters(self):
        cfg = AppConfig(openrouter_api_key=None, openrouter_models={})
        elders, using_openrouter = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert using_openrouter is False
        assert isinstance(elders["claude"], ClaudeCodeAdapter)
        assert isinstance(elders["gemini"], GeminiCLIAdapter)
        assert isinstance(elders["chatgpt"], CodexCLIAdapter)

    def test_cli_model_passes_through_to_subprocess_adapter(self):
        cfg = AppConfig(openrouter_api_key=None, openrouter_models={})
        elders, _ = build_elders(
            cfg,
            cli_models={"claude": "sonnet", "gemini": None, "chatgpt": None},
        )
        claude = elders["claude"]
        assert isinstance(claude, ClaudeCodeAdapter)
        assert claude.build_args("hi") == ["--model", "sonnet", "-p", "hi"]
