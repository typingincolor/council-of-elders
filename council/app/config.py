from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from council.domain.models import ElderId


@dataclass(frozen=True)
class AppConfig:
    openrouter_api_key: str | None = None
    openrouter_models: dict[ElderId, str] = field(default_factory=dict)


DEFAULT_CONFIG_PATH = Path.home() / ".council" / "config.toml"


def load_config(*, path: Path | None = None) -> AppConfig:
    _ = path or DEFAULT_CONFIG_PATH
    env_key = os.environ.get("OPENROUTER_API_KEY") or None
    return AppConfig(openrouter_api_key=env_key, openrouter_models={})
