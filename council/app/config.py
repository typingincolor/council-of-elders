from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from council.domain.models import ElderId

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppConfig:
    openrouter_api_key: str | None = None
    openrouter_models: dict[ElderId, str] = field(default_factory=dict)


DEFAULT_CONFIG_PATH = Path.home() / ".council" / "config.toml"

_VALID_ELDERS: tuple[ElderId, ...] = ("ada", "kai", "mei")


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except OSError as ex:
        log.warning("Config file %s is unreadable (%s); ignoring.", path, ex)
        return {}
    except tomllib.TOMLDecodeError as ex:
        raise tomllib.TOMLDecodeError(f"{path}: {ex}") from ex


def _resolve_key(toml_data: dict) -> str | None:
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key
    toml_key = toml_data.get("openrouter", {}).get("api_key")
    if isinstance(toml_key, str) and toml_key:
        return toml_key
    return None


_LEGACY_MODEL_KEYS: dict[str, ElderId] = {
    "claude": "ada",
    "gemini": "kai",
    "chatgpt": "mei",
}


def _resolve_models(toml_data: dict) -> dict[ElderId, str]:
    section = toml_data.get("openrouter", {}).get("models", {})
    out: dict[ElderId, str] = {}
    # Current-name keys take precedence over legacy-name keys.
    for legacy, current in _LEGACY_MODEL_KEYS.items():
        val = section.get(legacy)
        if isinstance(val, str) and val:
            log.warning(
                "Config key [openrouter.models].%s is deprecated; use "
                "[openrouter.models].%s instead.",
                legacy,
                current,
            )
            out[current] = val
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
