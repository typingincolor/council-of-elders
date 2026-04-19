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


from council.adapters.elders.openrouter import OpenRouterAdapter


class TestOpenRouterBranch:
    def test_key_present_builds_openrouter_adapters(self):
        cfg = AppConfig(openrouter_api_key="sk-or-x", openrouter_models={})
        elders, using_openrouter = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert using_openrouter is True
        for e in ("claude", "gemini", "chatgpt"):
            assert isinstance(elders[e], OpenRouterAdapter)

    def test_cli_model_wins_over_toml_and_defaults(self):
        cfg = AppConfig(
            openrouter_api_key="sk-or-x",
            openrouter_models={"claude": "toml/claude-model"},
        )
        elders, _ = build_elders(
            cfg,
            cli_models={
                "claude": "cli/claude-model",
                "gemini": None,
                "chatgpt": None,
            },
        )
        assert elders["claude"].model == "cli/claude-model"  # CLI wins
        assert elders["gemini"].model == "google/gemini-2.5-pro"  # default
        assert elders["chatgpt"].model == "openai/gpt-5"  # default

    def test_toml_model_wins_over_default(self):
        cfg = AppConfig(
            openrouter_api_key="sk-or-x",
            openrouter_models={"gemini": "toml/gemini-model"},
        )
        elders, _ = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert elders["gemini"].model == "toml/gemini-model"

    def test_api_key_propagates_to_adapters(self):
        cfg = AppConfig(openrouter_api_key="sk-or-abc", openrouter_models={})
        elders, _ = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        for e in ("claude", "gemini", "chatgpt"):
            assert elders[e].api_key == "sk-or-abc"
