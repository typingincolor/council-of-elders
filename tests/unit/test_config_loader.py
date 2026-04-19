"""Config loader: reads ~/.council/config.toml + env into an AppConfig."""

from __future__ import annotations

from pathlib import Path

from council.app.config import AppConfig, load_config


class TestMissingFile:
    def test_missing_file_returns_empty_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = load_config(path=tmp_path / "does-not-exist.toml")
        assert cfg == AppConfig(openrouter_api_key=None, openrouter_models={})


class TestTomlParse:
    def test_reads_api_key_and_models(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(
            """
[openrouter]
api_key = "sk-or-v1-abc"

[openrouter.models]
claude = "anthropic/claude-sonnet-4.5"
gemini = "google/gemini-2.5-pro"
chatgpt = "openai/gpt-5"
""".lstrip()
        )
        cfg = load_config(path=cfg_path)
        assert cfg.openrouter_api_key == "sk-or-v1-abc"
        assert cfg.openrouter_models == {
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        }

    def test_section_missing_leaves_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("# empty\n")
        cfg = load_config(path=cfg_path)
        assert cfg.openrouter_api_key is None
        assert cfg.openrouter_models == {}
