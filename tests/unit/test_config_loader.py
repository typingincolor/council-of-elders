"""Config loader: reads ~/.council/config.toml + env into an AppConfig."""

from __future__ import annotations

from pathlib import Path

from council.app.config import AppConfig, load_config


class TestMissingFile:
    def test_missing_file_returns_empty_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = load_config(path=tmp_path / "does-not-exist.toml")
        assert cfg == AppConfig(openrouter_api_key=None, openrouter_models={})
