from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from council.domain.models import ElderId


@dataclass(frozen=True)
class AppConfig:
    openrouter_api_key: str | None = None
    openrouter_models: dict[ElderId, str] = field(default_factory=dict)


DEFAULT_CONFIG_PATH = Path.home() / ".council" / "config.toml"

_VALID_ELDERS: tuple[ElderId, ...] = ("claude", "gemini", "chatgpt")


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _resolve_key(toml_data: dict) -> str | None:
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key
    toml_key = toml_data.get("openrouter", {}).get("api_key")
    if isinstance(toml_key, str) and toml_key:
        return toml_key
    return None


def _resolve_models(toml_data: dict) -> dict[ElderId, str]:
    section = toml_data.get("openrouter", {}).get("models", {})
    out: dict[ElderId, str] = {}
    for elder in _VALID_ELDERS:
        val = section.get(elder)
        if isinstance(val, str) and val:
            out[elder] = val
    return out


def load_config(*, path: Path | None = None) -> AppConfig:
    target = path or DEFAULT_CONFIG_PATH
    toml_data = _read_toml(target)
    return AppConfig(
        openrouter_api_key=_resolve_key(toml_data),
        openrouter_models=_resolve_models(toml_data),
    )
