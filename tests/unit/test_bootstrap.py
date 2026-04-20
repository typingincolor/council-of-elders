"""build_elders() decides between OpenRouter and subprocess adapters."""

from __future__ import annotations

from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.elders.openrouter import OpenRouterAdapter
from council.app.bootstrap import build_elders
from council.app.config import AppConfig
from council.domain.roster import RosterSpec


class TestSubprocessBranch:
    def test_no_key_builds_subprocess_adapters(self):
        cfg = AppConfig(openrouter_api_key=None, openrouter_models={})
        elders, using_openrouter, _ = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert using_openrouter is False
        assert isinstance(elders["claude"], ClaudeCodeAdapter)
        assert isinstance(elders["gemini"], GeminiCLIAdapter)
        assert isinstance(elders["chatgpt"], CodexCLIAdapter)

    def test_cli_model_passes_through_to_subprocess_adapter(self):
        cfg = AppConfig(openrouter_api_key=None, openrouter_models={})
        elders, _, _ = build_elders(
            cfg,
            cli_models={"claude": "sonnet", "gemini": None, "chatgpt": None},
        )
        claude = elders["claude"]
        assert isinstance(claude, ClaudeCodeAdapter)
        assert claude.build_args("hi") == ["--model", "sonnet", "-p", "hi"]


class TestOpenRouterBranch:
    def test_key_present_builds_openrouter_adapters(self):
        cfg = AppConfig(openrouter_api_key="sk-or-x", openrouter_models={})
        elders, using_openrouter, _ = build_elders(
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
        elders, _, _ = build_elders(
            cfg,
            cli_models={
                "claude": "cli/claude-model",
                "gemini": None,
                "chatgpt": None,
            },
        )
        assert elders["claude"].model == "cli/claude-model"  # CLI wins
        assert elders["gemini"].model == "meta-llama/llama-3.1-70b-instruct"  # default
        assert elders["chatgpt"].model == "openai/gpt-5"  # default

    def test_toml_model_wins_over_default(self):
        cfg = AppConfig(
            openrouter_api_key="sk-or-x",
            openrouter_models={"gemini": "toml/gemini-model"},
        )
        elders, _, _ = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert elders["gemini"].model == "toml/gemini-model"

    def test_api_key_propagates_to_adapters(self):
        cfg = AppConfig(openrouter_api_key="sk-or-abc", openrouter_models={})
        elders, _, _ = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        for e in ("claude", "gemini", "chatgpt"):
            assert elders[e].api_key == "sk-or-abc"


class TestRosterSpecReturned:
    def test_openrouter_branch_returns_real_spec(self):
        cfg = AppConfig(openrouter_api_key="sk-or-x", openrouter_models={})
        _, using_or, spec = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert using_or is True
        assert isinstance(spec, RosterSpec)
        assert spec.name == "openrouter"
        assert spec.models["claude"] == "anthropic/claude-sonnet-4.5"
        assert spec.models["gemini"] == "meta-llama/llama-3.1-70b-instruct"
        assert spec.models["chatgpt"] == "openai/gpt-5"

    def test_openrouter_spec_reflects_cli_and_toml_overrides(self):
        cfg = AppConfig(
            openrouter_api_key="sk-or-x",
            openrouter_models={"gemini": "toml/gemini-model"},
        )
        _, _, spec = build_elders(
            cfg,
            cli_models={
                "claude": "cli/claude-model",
                "gemini": None,
                "chatgpt": None,
            },
        )
        assert spec.models["claude"] == "cli/claude-model"
        assert spec.models["gemini"] == "toml/gemini-model"
        assert spec.models["chatgpt"] == "openai/gpt-5"

    def test_subprocess_branch_returns_sentinel_spec(self):
        cfg = AppConfig(openrouter_api_key=None, openrouter_models={})
        _, using_or, spec = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert using_or is False
        assert isinstance(spec, RosterSpec)
        assert spec.name == "subprocess"
        assert spec.models == {}
