"""Config loader: reads ~/.council/config.toml + env into an AppConfig."""

from __future__ import annotations

import logging
import tomllib
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
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "google/gemini-2.5-pro",
            "mei": "openai/gpt-5",
        }

    def test_section_missing_leaves_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("# empty\n")
        cfg = load_config(path=cfg_path)
        assert cfg.openrouter_api_key is None
        assert cfg.openrouter_models == {}


class TestKeyPrecedence:
    def test_env_overrides_toml_key(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "env-wins")
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('[openrouter]\napi_key = "toml-loses"\n')
        cfg = load_config(path=cfg_path)
        assert cfg.openrouter_api_key == "env-wins"

    def test_empty_env_value_treated_as_absent(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('[openrouter]\napi_key = "from-toml"\n')
        cfg = load_config(path=cfg_path)
        assert cfg.openrouter_api_key == "from-toml"

    def test_env_only_no_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "env-only")
        cfg = load_config(path=tmp_path / "missing.toml")
        assert cfg.openrouter_api_key == "env-only"
        assert cfg.openrouter_models == {}


class TestErrorHandling:
    def test_malformed_toml_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg_path = tmp_path / "bad.toml"
        cfg_path.write_text("this is = not [ valid toml\n")
        import pytest as _pytest

        with _pytest.raises(tomllib.TOMLDecodeError) as exc_info:
            load_config(path=cfg_path)
        assert str(cfg_path) in str(exc_info.value)

    def test_unreadable_file_warns_and_returns_empty(self, tmp_path: Path, monkeypatch, caplog):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg_path = tmp_path / "locked.toml"
        cfg_path.write_text('[openrouter]\napi_key = "x"\n')
        cfg_path.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING):
                cfg = load_config(path=cfg_path)
        finally:
            cfg_path.chmod(0o644)
        assert cfg.openrouter_api_key is None
        assert any("unreadable" in rec.message.lower() for rec in caplog.records)
