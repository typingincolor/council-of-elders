# OpenRouter Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenRouter as an alternative transport for all three elders, activated when an API key is resolvable from `~/.council/config.toml` or `OPENROUTER_API_KEY` env var; show per-session cost and remaining credit.

**Architecture:** New `OpenRouterAdapter` implements the existing `ElderPort` protocol over `httpx`. A new `council/app/config.py` loads TOML + env settings into a frozen `AppConfig`. A new `council/app/bootstrap.py::build_elders()` is the single place where the TUI and headless entry points decide between OpenRouter and the existing subprocess adapters. Domain code is untouched.

**Tech Stack:** Python 3.12, `httpx>=0.27` (new), stdlib `tomllib`, `textual` (unchanged), `pytest` + `pytest-asyncio`.

**Companion spec:** `docs/superpowers/specs/2026-04-19-openrouter-config-design.md`.

---

## File map

| Path | Create / Modify | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Add `httpx>=0.27` runtime dep |
| `council/app/config.py` | Create | `AppConfig` dataclass + `load_config()` |
| `council/adapters/elders/openrouter.py` | Create | `OpenRouterAdapter` + `OpenRouterError` |
| `council/app/bootstrap.py` | Create | `build_elders()` + default model constants |
| `council/app/tui/app.py` | Modify | Use `build_elders`; surface cost after each round |
| `council/app/headless/main.py` | Modify | Use `build_elders`; print final cost summary |
| `tests/unit/test_config_loader.py` | Create | Precedence, missing-file, malformed-TOML |
| `tests/unit/test_openrouter_adapter.py` | Create | Request shape, error mapping, cost capture, credits |
| `tests/unit/test_bootstrap.py` | Create | Branch selection, model precedence |
| `tests/contract/test_elder_port_contract.py` | Modify | Add `OpenRouterAdapter` under mock transport |
| `tests/integration/test_openrouter_smoke.py` | Create | Real API round-trip when key present |
| `README.md` | Modify | OpenRouter sidebar + config example |
| `docs/USAGE.md` | Modify | "Using OpenRouter" section |

---

### Task 1: Add httpx dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `httpx>=0.27` to the runtime `dependencies` array**

In `pyproject.toml`, change the `dependencies` block:

```toml
dependencies = [
    "textual>=0.85",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Reinstall the project so the dependency is available in the venv**

Run: `uv pip install -e .`
Expected: `httpx` is installed (last line resembles `Installed N packages`).

- [ ] **Step 3: Verify the import works**

Run: `python -c "import httpx; print(httpx.__version__)"`
Expected: A version number `>= 0.27.0` prints.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add httpx for OpenRouter adapter"
```

---

### Task 2: Config loader — empty defaults when file absent

**Files:**
- Create: `council/app/config.py`
- Test: `tests/unit/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config_loader.py`:

```python
"""Config loader: reads ~/.council/config.toml + env into an AppConfig."""

from __future__ import annotations

from pathlib import Path

from council.app.config import AppConfig, load_config


class TestMissingFile:
    def test_missing_file_returns_empty_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = load_config(path=tmp_path / "does-not-exist.toml")
        assert cfg == AppConfig(openrouter_api_key=None, openrouter_models={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'council.app.config'`.

- [ ] **Step 3: Write the minimal implementation**

Create `council/app/config.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/app/config.py tests/unit/test_config_loader.py
git commit -m "feat(config): load_config stub returning empty AppConfig"
```

---

### Task 3: Config loader — parse TOML `[openrouter]` section

**Files:**
- Modify: `council/app/config.py`
- Modify: `tests/unit/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_config_loader.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: The two new tests FAIL (api_key still `None`, models still empty).

- [ ] **Step 3: Update the implementation to parse TOML**

Replace the body of `council/app/config.py`:

```python
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
```

- [ ] **Step 4: Run all config tests**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: All three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/app/config.py tests/unit/test_config_loader.py
git commit -m "feat(config): parse [openrouter] section from TOML"
```

---

### Task 4: Config loader — env var wins over TOML; empty env treated as absent

**Files:**
- Modify: `tests/unit/test_config_loader.py`

The implementation from Task 3 already does this (env first, then TOML, with empty string falsy). Add tests to lock the behaviour in.

- [ ] **Step 1: Append the precedence tests**

Append to `tests/unit/test_config_loader.py`:

```python
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: All six tests PASS (no implementation change needed — Task 3's `_resolve_key` already handles this).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_config_loader.py
git commit -m "test(config): lock in env-wins-over-TOML precedence"
```

---

### Task 5: Config loader — malformed TOML raises; unreadable file warns and falls back

**Files:**
- Modify: `council/app/config.py`
- Modify: `tests/unit/test_config_loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config_loader.py`:

```python
import logging
import tomllib


class TestErrorHandling:
    def test_malformed_toml_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg_path = tmp_path / "bad.toml"
        cfg_path.write_text("this is = not [ valid toml\n")
        import pytest as _pytest

        with _pytest.raises(tomllib.TOMLDecodeError) as exc_info:
            load_config(path=cfg_path)
        assert str(cfg_path) in str(exc_info.value)

    def test_unreadable_file_warns_and_returns_empty(
        self, tmp_path: Path, monkeypatch, caplog
    ):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: Both new tests FAIL — current `_read_toml` doesn't prefix the path on parse errors and doesn't catch `OSError`.

- [ ] **Step 3: Update `_read_toml` to handle errors**

In `council/app/config.py`, replace `_read_toml` with:

```python
import logging

log = logging.getLogger(__name__)


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
```

(Keep the existing `import tomllib` at the top of the module; `import logging` is new — add it alongside the other imports.)

- [ ] **Step 4: Run all config tests**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: All eight tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/app/config.py tests/unit/test_config_loader.py
git commit -m "feat(config): prefix path on TOML parse errors; warn on unreadable file"
```

---

### Task 6: OpenRouter adapter — skeleton, constructor, health check

**Files:**
- Create: `council/adapters/elders/openrouter.py`
- Create: `tests/unit/test_openrouter_adapter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_openrouter_adapter.py`:

```python
"""Unit tests for OpenRouterAdapter using httpx.MockTransport (no network)."""

from __future__ import annotations

import pytest

from council.adapters.elders.openrouter import OpenRouterAdapter, OpenRouterError


class TestConstructorAndHealth:
    def test_exposes_elder_id(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="anthropic/claude-sonnet-4.5", api_key="sk-or-x"
        )
        assert a.elder_id == "claude"

    async def test_health_check_true_when_key_set(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="anthropic/claude-sonnet-4.5", api_key="sk-or-x"
        )
        assert await a.health_check() is True

    async def test_health_check_false_when_key_empty(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="anthropic/claude-sonnet-4.5", api_key=""
        )
        assert await a.health_check() is False

    def test_error_class_has_kind_and_detail(self):
        e = OpenRouterError("auth_failed", "bad key")
        assert e.kind == "auth_failed"
        assert e.detail == "bad key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create the adapter skeleton**

Create `council/adapters/elders/openrouter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from council.domain.models import ElderId, ErrorKind


class OpenRouterError(Exception):
    def __init__(self, kind: ErrorKind, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind: ErrorKind = kind
        self.detail: str = detail


@dataclass
class OpenRouterAdapter:
    elder_id: ElderId
    model: str
    api_key: str
    client: httpx.AsyncClient | None = None
    session_cost_usd: float = 0.0
    session_tokens: dict[str, int] = field(
        default_factory=lambda: {"prompt": 0, "completion": 0}
    )

    async def ask(self, prompt: str, *, timeout_s: float = 45.0) -> str:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return bool(self.api_key)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/openrouter.py tests/unit/test_openrouter_adapter.py
git commit -m "feat(adapter): OpenRouterAdapter skeleton + health_check"
```

---

### Task 7: OpenRouter adapter — happy path `ask()`

**Files:**
- Modify: `council/adapters/elders/openrouter.py`
- Modify: `tests/unit/test_openrouter_adapter.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_openrouter_adapter.py`:

```python
import httpx


def _adapter_with_transport(transport: httpx.MockTransport) -> OpenRouterAdapter:
    return OpenRouterAdapter(
        elder_id="claude",
        model="anthropic/claude-sonnet-4.5",
        api_key="sk-or-test",
        client=httpx.AsyncClient(transport=transport, base_url="https://openrouter.ai"),
    )


class TestAskHappyPath:
    async def test_returns_message_content(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "gen-1",
                    "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                        "cost": 0.0005,
                    },
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        reply = await a.ask("hi")
        assert reply == "hello"

    async def test_sends_expected_request(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={
                    "id": "gen-1",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        await a.ask("hello world")

        import json as _json

        assert len(captured) == 1
        req = captured[0]
        assert req.method == "POST"
        assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-or-test"
        assert req.headers["Content-Type"].startswith("application/json")
        body = _json.loads(req.content)
        assert body["model"] == "anthropic/claude-sonnet-4.5"
        assert body["messages"] == [{"role": "user", "content": "hello world"}]
        assert body["usage"] == {"include": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_openrouter_adapter.py::TestAskHappyPath -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `ask()` happy path**

Replace the `ask` body in `council/adapters/elders/openrouter.py`:

```python
_BASE_URL = "https://openrouter.ai"
_CHAT_PATH = "/api/v1/chat/completions"
_REFERER = "https://github.com/typingincolor/council-of-elders"
_TITLE = "council-of-elders"


async def _post_chat(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    prompt: str,
    timeout_s: float,
) -> httpx.Response:
    return await client.post(
        _CHAT_PATH,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": _REFERER,
            "X-Title": _TITLE,
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "usage": {"include": True},
        },
        timeout=timeout_s,
    )


# ... inside OpenRouterAdapter:

    async def ask(self, prompt: str, *, timeout_s: float = 45.0) -> str:
        client = self.client or httpx.AsyncClient(base_url=_BASE_URL)
        owned = self.client is None
        try:
            resp = await _post_chat(client, self.api_key, self.model, prompt, timeout_s)
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        finally:
            if owned:
                await client.aclose()
```

Note: put the module-level constants (`_BASE_URL`, `_CHAT_PATH`, `_REFERER`, `_TITLE`) and `_post_chat` helper at the top of the module, above the class definition.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/openrouter.py tests/unit/test_openrouter_adapter.py
git commit -m "feat(adapter): OpenRouterAdapter ask() happy path"
```

---

### Task 8: OpenRouter adapter — error classification

**Files:**
- Modify: `council/adapters/elders/openrouter.py`
- Modify: `tests/unit/test_openrouter_adapter.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_openrouter_adapter.py`:

```python
class TestAskErrorMapping:
    async def test_401_maps_to_auth_failed(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid key"}})

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "auth_failed"

    async def test_403_maps_to_auth_failed(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "auth_failed"

    async def test_429_maps_to_quota_exhausted(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="slow down")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "quota_exhausted"

    async def test_500_maps_to_nonzero_exit(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server exploded")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "nonzero_exit"
        assert "500" in ei.value.detail

    async def test_malformed_json_maps_to_unparseable(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"weird": True})

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "unparseable"

    async def test_timeout_maps_to_timeout(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("slow")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi", timeout_s=0.1)
        assert ei.value.kind == "timeout"

    async def test_network_error_maps_to_nonzero_exit(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "nonzero_exit"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_openrouter_adapter.py::TestAskErrorMapping -v`
Expected: FAIL — adapter currently swallows errors as `KeyError` / raw httpx exceptions.

- [ ] **Step 3: Implement error mapping**

Replace the `ask` method in `council/adapters/elders/openrouter.py`:

```python
    async def ask(self, prompt: str, *, timeout_s: float = 45.0) -> str:
        client = self.client or httpx.AsyncClient(base_url=_BASE_URL)
        owned = self.client is None
        try:
            try:
                resp = await _post_chat(
                    client, self.api_key, self.model, prompt, timeout_s
                )
            except httpx.TimeoutException as ex:
                raise OpenRouterError("timeout", str(ex)) from ex
            except httpx.HTTPError as ex:
                raise OpenRouterError("nonzero_exit", f"network error: {ex}") from ex

            if resp.status_code in (401, 403):
                raise OpenRouterError("auth_failed", resp.text[-400:])
            if resp.status_code == 429:
                raise OpenRouterError("quota_exhausted", resp.text[-400:])
            if resp.status_code >= 400:
                raise OpenRouterError(
                    "nonzero_exit", f"HTTP {resp.status_code}: {resp.text[-400:]}"
                )

            try:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as ex:
                raise OpenRouterError(
                    "unparseable", f"unexpected response shape: {ex}"
                ) from ex
        finally:
            if owned:
                await client.aclose()
```

- [ ] **Step 4: Run all adapter tests**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/openrouter.py tests/unit/test_openrouter_adapter.py
git commit -m "feat(adapter): classify OpenRouter HTTP errors by kind"
```

---

### Task 9: OpenRouter adapter — session cost / token accumulation

**Files:**
- Modify: `council/adapters/elders/openrouter.py`
- Modify: `tests/unit/test_openrouter_adapter.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_openrouter_adapter.py`:

```python
class TestCostCapture:
    async def test_accumulates_cost_and_tokens_across_calls(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [{"message": {"content": "reply"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "cost": 0.001,
                    },
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        await a.ask("one")
        await a.ask("two")
        assert a.session_cost_usd == pytest.approx(0.002)
        assert a.session_tokens == {"prompt": 20, "completion": 10}

    async def test_missing_cost_leaves_total_unchanged(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [{"message": {"content": "reply"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        await a.ask("hi")
        assert a.session_cost_usd == 0.0
        assert a.session_tokens == {"prompt": 1, "completion": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_openrouter_adapter.py::TestCostCapture -v`
Expected: FAIL — `session_cost_usd` stays `0.0`.

- [ ] **Step 3: Update `ask()` to accumulate usage**

In `council/adapters/elders/openrouter.py`, update the success branch of `ask()` so it captures usage **before** returning:

```python
            try:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as ex:
                raise OpenRouterError(
                    "unparseable", f"unexpected response shape: {ex}"
                ) from ex

            usage = data.get("usage") or {}
            cost = usage.get("cost")
            if isinstance(cost, (int, float)):
                self.session_cost_usd += float(cost)
            self.session_tokens["prompt"] += int(usage.get("prompt_tokens") or 0)
            self.session_tokens["completion"] += int(usage.get("completion_tokens") or 0)
            return content
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/openrouter.py tests/unit/test_openrouter_adapter.py
git commit -m "feat(adapter): accumulate session cost and tokens from usage"
```

---

### Task 10: OpenRouter adapter — `fetch_credits()`

**Files:**
- Modify: `council/adapters/elders/openrouter.py`
- Modify: `tests/unit/test_openrouter_adapter.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_openrouter_adapter.py`:

```python
class TestFetchCredits:
    async def test_returns_used_and_limit(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/credits"
            return httpx.Response(
                200,
                json={"data": {"total_credits": 10.0, "total_usage": 2.5}},
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        used, limit = await a.fetch_credits()
        assert used == pytest.approx(2.5)
        assert limit == pytest.approx(10.0)

    async def test_missing_data_returns_safe_default(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        a = _adapter_with_transport(httpx.MockTransport(handler))
        used, limit = await a.fetch_credits()
        assert used == 0.0
        assert limit is None

    async def test_http_error_returns_safe_default(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        used, limit = await a.fetch_credits()
        assert used == 0.0
        assert limit is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_openrouter_adapter.py::TestFetchCredits -v`
Expected: FAIL — method doesn't exist.

- [ ] **Step 3: Implement `fetch_credits`**

Add to `OpenRouterAdapter` in `council/adapters/elders/openrouter.py`:

```python
    async def fetch_credits(self) -> tuple[float, float | None]:
        client = self.client or httpx.AsyncClient(base_url=_BASE_URL)
        owned = self.client is None
        try:
            try:
                resp = await client.get(
                    "/api/v1/credits",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                data = resp.json().get("data", {}) if resp.status_code == 200 else {}
            except (httpx.HTTPError, ValueError):
                return (0.0, None)
            used = float(data.get("total_usage") or 0.0)
            limit_raw = data.get("total_credits")
            limit = float(limit_raw) if isinstance(limit_raw, (int, float)) else None
            return (used, limit)
        finally:
            if owned:
                await client.aclose()
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/openrouter.py tests/unit/test_openrouter_adapter.py
git commit -m "feat(adapter): fetch_credits() returns (used, limit)"
```

---

### Task 11: Contract test — `OpenRouterAdapter` upholds the `ElderPort` contract

**Files:**
- Modify: `tests/contract/test_elder_port_contract.py`

- [ ] **Step 1: Extend the contract test to include OpenRouter**

Replace `tests/contract/test_elder_port_contract.py` with:

```python
"""Contract tests every ElderPort implementation must satisfy.

FakeElder always runs. Real-CLI adapters are parameterized with the
`integration` marker, so they only run under `pytest -m integration`
(the default pytest config uses `-m 'not integration'`).
"""

from __future__ import annotations

import httpx
import pytest

from council.adapters.elders.fake import FakeElder


def _fake_elder():
    return FakeElder(
        elder_id="claude",
        replies=["The first answer.\nCONVERGED: yes"],
    )


def _openrouter_mocked():
    from council.adapters.elders.openrouter import OpenRouterAdapter

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "gen-contract",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
            },
        )

    return OpenRouterAdapter(
        elder_id="claude",
        model="anthropic/claude-sonnet-4.5",
        api_key="sk-or-contract",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://openrouter.ai",
        ),
    )


def _claude_real():
    from council.adapters.elders.claude_code import ClaudeCodeAdapter

    return ClaudeCodeAdapter()


def _gemini_real():
    from council.adapters.elders.gemini_cli import GeminiCLIAdapter

    return GeminiCLIAdapter()


def _codex_real():
    from council.adapters.elders.codex_cli import CodexCLIAdapter

    return CodexCLIAdapter()


ELDERS_UNDER_CONTRACT = [
    pytest.param(_fake_elder, id="fake"),
    pytest.param(_openrouter_mocked, id="openrouter-mocked"),
    pytest.param(_claude_real, id="claude-real", marks=pytest.mark.integration),
    pytest.param(_gemini_real, id="gemini-real", marks=pytest.mark.integration),
    pytest.param(_codex_real, id="codex-real", marks=pytest.mark.integration),
]


@pytest.fixture(params=ELDERS_UNDER_CONTRACT)
def elder_factory(request):
    return request.param


class TestElderPortContract:
    async def test_ask_returns_nonempty_string(self, elder_factory):
        elder = elder_factory()
        reply = await elder.ask("Say hello.", timeout_s=60)
        assert isinstance(reply, str)
        assert reply.strip()

    async def test_health_check_is_bool(self, elder_factory):
        elder = elder_factory()
        result = await elder.health_check()
        assert isinstance(result, bool)
```

- [ ] **Step 2: Run the contract tests**

Run: `pytest tests/contract/test_elder_port_contract.py -v`
Expected: `fake` and `openrouter-mocked` parameters PASS; real-CLI params are deselected by the default `-m 'not integration'` filter.

- [ ] **Step 3: Commit**

```bash
git add tests/contract/test_elder_port_contract.py
git commit -m "test(contract): verify OpenRouterAdapter upholds ElderPort"
```

---

### Task 12: Bootstrap — subprocess branch (no key)

**Files:**
- Create: `council/app/bootstrap.py`
- Create: `tests/unit/test_bootstrap.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_bootstrap.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_bootstrap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'council.app.bootstrap'`.

- [ ] **Step 3: Create the bootstrap module**

Create `council/app/bootstrap.py`:

```python
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
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/unit/test_bootstrap.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/app/bootstrap.py tests/unit/test_bootstrap.py
git commit -m "feat(bootstrap): build_elders subprocess branch"
```

---

### Task 13: Bootstrap — OpenRouter branch with model precedence

**Files:**
- Modify: `council/app/bootstrap.py`
- Modify: `tests/unit/test_bootstrap.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_bootstrap.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_bootstrap.py::TestOpenRouterBranch -v`
Expected: FAIL — `NotImplementedError` from the stub.

- [ ] **Step 3: Implement the OpenRouter branch**

Replace `build_elders` in `council/app/bootstrap.py`:

```python
from council.adapters.elders.openrouter import OpenRouterAdapter


def build_elders(
    config: AppConfig,
    *,
    cli_models: dict[ElderId, str | None],
) -> tuple[dict[ElderId, ElderPort], bool]:
    if config.openrouter_api_key:
        elders: dict[ElderId, ElderPort] = {}
        for eid in ("claude", "gemini", "chatgpt"):
            model = (
                cli_models.get(eid)
                or config.openrouter_models.get(eid)
                or _DEFAULT_OPENROUTER_MODELS[eid]
            )
            elders[eid] = OpenRouterAdapter(
                elder_id=eid,
                model=model,
                api_key=config.openrouter_api_key,
            )
        return elders, True

    elders = {
        "claude": ClaudeCodeAdapter(model=cli_models.get("claude")),
        "gemini": GeminiCLIAdapter(model=cli_models.get("gemini")),
        "chatgpt": CodexCLIAdapter(model=cli_models.get("chatgpt")),
    }
    return elders, False
```

(Put the `OpenRouterAdapter` import with the other adapter imports at the top of the module.)

- [ ] **Step 4: Run all bootstrap tests**

Run: `pytest tests/unit/test_bootstrap.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/app/bootstrap.py tests/unit/test_bootstrap.py
git commit -m "feat(bootstrap): build OpenRouter adapters with model precedence"
```

---

### Task 14: Wire headless entry point through `build_elders`

**Files:**
- Modify: `council/app/headless/main.py`

- [ ] **Step 1: Replace the elder-dict construction in `main()`**

In `council/app/headless/main.py`, at the top of the file add:

```python
from council.app.bootstrap import build_elders
from council.app.config import load_config
```

Then replace the `elders: dict[ElderId, ElderPort] = {...}` block in `main()` with:

```python
    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "claude": args.claude_model,
        "gemini": args.gemini_model,
        "chatgpt": args.codex_model,
    }
    elders, _using_openrouter = build_elders(config, cli_models=cli_models)
```

(The unused `ClaudeCodeAdapter` / `GeminiCLIAdapter` / `CodexCLIAdapter` imports can be removed — they're now only touched by `bootstrap.py`.)

- [ ] **Step 2: Verify headless still runs its existing smoke path**

Run: `pytest tests/ -v -x`
Expected: All currently-passing tests still pass; nothing regressed.

- [ ] **Step 3: Commit**

```bash
git add council/app/headless/main.py
git commit -m "refactor(headless): build elders through bootstrap + config"
```

---

### Task 15: Wire TUI entry point through `build_elders`

**Files:**
- Modify: `council/app/tui/app.py`

- [ ] **Step 1: Add imports at the top of `council/app/tui/app.py`**

```python
from council.app.bootstrap import build_elders
from council.app.config import load_config
```

- [ ] **Step 2: Replace the elder-dict in `main()`**

Find the block in `main()` that reads:

```python
    app = CouncilApp(
        elders={
            "claude": ClaudeCodeAdapter(model=args.claude_model),
            "gemini": GeminiCLIAdapter(model=args.gemini_model),
            "chatgpt": CodexCLIAdapter(model=args.codex_model),
        },
```

Replace with:

```python
    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "claude": args.claude_model,
        "gemini": args.gemini_model,
        "chatgpt": args.codex_model,
    }
    elders, using_openrouter = build_elders(config, cli_models=cli_models)

    app = CouncilApp(
        elders=elders,
```

And store `using_openrouter` on the app instance (needed in the next task). Update `CouncilApp.__init__` signature: add a keyword-only `using_openrouter: bool = False` parameter stored as `self._using_openrouter`. Pass it at construction: `using_openrouter=using_openrouter`.

Remove now-unused imports (`ClaudeCodeAdapter`, `GeminiCLIAdapter`, `CodexCLIAdapter`) if nothing else in the module references them.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v -x`
Expected: All tests PASS; no regression.

- [ ] **Step 4: Manual smoke of the TUI**

Run: `council --help`
Expected: The existing CLI help prints normally; no import errors.

- [ ] **Step 5: Commit**

```bash
git add council/app/tui/app.py
git commit -m "refactor(tui): build elders through bootstrap + config"
```

---

### Task 16: TUI cost surfacing after each round

**Files:**
- Modify: `council/app/tui/app.py`
- Modify: `council/app/headless/main.py` (re-use helper if clean, or duplicate)

- [ ] **Step 1: Add a formatter helper in `council/adapters/elders/openrouter.py`**

Append to `council/adapters/elders/openrouter.py`:

```python
def format_cost_notice(
    elders: dict,  # dict[ElderId, ElderPort]
    round_cost_delta_usd: float,
    credits_used: float,
    credits_limit: float | None,
) -> str:
    session_total = sum(
        getattr(e, "session_cost_usd", 0.0) for e in elders.values()
    )
    parts = [
        "[openrouter]",
        f"round: ${round_cost_delta_usd:.4f}",
        f"session: ${session_total:.4f}",
    ]
    if credits_limit is not None:
        remaining = max(credits_limit - credits_used, 0.0)
        parts.append(f"credits remaining: ${remaining:.2f}")
    else:
        parts.append(f"credits used: ${credits_used:.2f}")
    return " · ".join(parts)
```

- [ ] **Step 2: Update `_consume_events` in `council/app/tui/app.py`**

In the `elif isinstance(ev, RoundCompleted):` branch of `_consume_events`, add cost surfacing only when OpenRouter is active. The new branch body:

```python
            elif isinstance(ev, RoundCompleted):
                self.awaiting_decision = True
                self.query_one("#input", CouncilInput).disabled = False
                if self._using_openrouter:
                    self._spawn(self._write_cost_notice())
```

Then add a new method to `CouncilApp`:

```python
    async def _write_cost_notice(self) -> None:
        from council.adapters.elders.openrouter import (
            OpenRouterAdapter,
            format_cost_notice,
        )

        # Compute round delta by subtracting previously-seen total
        prev = getattr(self, "_prev_cost_total", 0.0)
        current = sum(
            e.session_cost_usd
            for e in self._elders.values()
            if isinstance(e, OpenRouterAdapter)
        )
        self._prev_cost_total = current
        delta = current - prev

        # Credits fetched from any one OpenRouter adapter (same key)
        any_or = next(
            (e for e in self._elders.values() if isinstance(e, OpenRouterAdapter)),
            None,
        )
        used, limit = (0.0, None)
        if any_or is not None:
            used, limit = await any_or.fetch_credits()

        line = format_cost_notice(
            elders=self._elders,
            round_cost_delta_usd=delta,
            credits_used=used,
            credits_limit=limit,
        )
        self._write_notice(f"[blue]{line}[/blue]")
```

Initialise `self._prev_cost_total = 0.0` in `CouncilApp.__init__`.

- [ ] **Step 3: Add a TUI unit test for the formatter**

Append to `tests/unit/test_openrouter_adapter.py`:

```python
from council.adapters.elders.openrouter import format_cost_notice


class TestFormatCostNotice:
    def test_with_known_limit_shows_remaining(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="x", api_key="k"
        )
        a.session_cost_usd = 0.10
        b = OpenRouterAdapter(
            elder_id="gemini", model="x", api_key="k"
        )
        b.session_cost_usd = 0.05
        line = format_cost_notice(
            elders={"claude": a, "gemini": b},
            round_cost_delta_usd=0.03,
            credits_used=2.5,
            credits_limit=10.0,
        )
        assert "round: $0.0300" in line
        assert "session: $0.1500" in line
        assert "credits remaining: $7.50" in line

    def test_with_no_limit_shows_used(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="x", api_key="k"
        )
        line = format_cost_notice(
            elders={"claude": a},
            round_cost_delta_usd=0.01,
            credits_used=3.25,
            credits_limit=None,
        )
        assert "credits used: $3.25" in line
        assert "remaining" not in line
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_openrouter_adapter.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/openrouter.py council/app/tui/app.py tests/unit/test_openrouter_adapter.py
git commit -m "feat(tui): surface OpenRouter cost and credits after each round"
```

---

### Task 17: Headless cost summary after synthesis

**Files:**
- Modify: `council/app/headless/main.py`

- [ ] **Step 1: Update `run_headless` to print the cost line when OpenRouter is active**

In `council/app/headless/main.py`, change `run_headless`'s signature to accept `using_openrouter: bool` (keyword-only) and print a summary after `synth`:

```python
async def run_headless(
    prompt: str,
    pack: CouncilPack,
    elders: dict[ElderId, ElderPort],
    store: TranscriptStore,
    clock: Clock,
    bus: EventBus,
    synthesizer: ElderId,
    *,
    using_openrouter: bool = False,
) -> None:
    # ... existing body up to the synthesis print ...
    print(f"[Synthesis by {_LABELS[synthesizer]}] {synth.text}")
    if using_openrouter:
        from council.adapters.elders.openrouter import (
            OpenRouterAdapter,
            format_cost_notice,
        )

        any_or = next(
            (e for e in elders.values() if isinstance(e, OpenRouterAdapter)),
            None,
        )
        used, limit = (0.0, None)
        if any_or is not None:
            used, limit = await any_or.fetch_credits()
        total = sum(
            e.session_cost_usd
            for e in elders.values()
            if isinstance(e, OpenRouterAdapter)
        )
        line = format_cost_notice(
            elders=elders,
            round_cost_delta_usd=total,  # single "round" = whole session for headless
            credits_used=used,
            credits_limit=limit,
        )
        print(line)
```

And in `main()`, pass the flag into `run_headless`:

```python
    elders, using_openrouter = build_elders(config, cli_models=cli_models)
    asyncio.run(
        run_headless(
            prompt=args.prompt,
            pack=pack,
            elders=elders,
            store=JsonFileStore(root=Path(args.store_root)),
            clock=SystemClock(),
            bus=InMemoryBus(),
            synthesizer=args.synthesizer,
            using_openrouter=using_openrouter,
        )
    )
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v -x`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add council/app/headless/main.py
git commit -m "feat(headless): print cost summary when OpenRouter is active"
```

---

### Task 18: Integration smoke test against real OpenRouter

**Files:**
- Create: `tests/integration/test_openrouter_smoke.py`

- [ ] **Step 1: Add the smoke test**

Create `tests/integration/test_openrouter_smoke.py`:

```python
"""Hits the real OpenRouter API. Skipped unless OPENROUTER_API_KEY is set."""

from __future__ import annotations

import os

import pytest

from council.adapters.elders.openrouter import OpenRouterAdapter


@pytest.mark.integration
async def test_openrouter_round_trip():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    adapter = OpenRouterAdapter(
        elder_id="claude",
        model="openai/gpt-4o-mini",  # cheap, widely available
        api_key=key,
    )
    reply = await adapter.ask("Say exactly the word 'hi' and nothing else.", timeout_s=30)
    assert reply.strip()


@pytest.mark.integration
async def test_openrouter_fetch_credits():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    adapter = OpenRouterAdapter(
        elder_id="claude",
        model="openai/gpt-4o-mini",
        api_key=key,
    )
    used, limit = await adapter.fetch_credits()
    assert used >= 0.0
    assert limit is None or limit >= 0.0
```

- [ ] **Step 2: Verify it is skipped by default**

Run: `pytest tests/integration/test_openrouter_smoke.py -v`
Expected: Two `SKIPPED` (no `OPENROUTER_API_KEY` env var in the default environment — or the tests get deselected by `-m 'not integration'`). Either outcome is acceptable; no failures.

- [ ] **Step 3: If you have an OPENROUTER_API_KEY available, try the integration path**

Run: `pytest tests/integration/test_openrouter_smoke.py -v -m integration`
Expected: Either PASS (if a key is exported) or SKIPPED (if not). Should never FAIL.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_openrouter_smoke.py
git commit -m "test(integration): smoke test for OpenRouter adapter"
```

---

### Task 19: Update user docs

**Files:**
- Modify: `README.md`
- Modify: `docs/USAGE.md`

- [ ] **Step 1: Add "Using OpenRouter" section to `README.md`**

Insert the following block under the `## Quick start` section (before `### Participating in the debate`):

````markdown
### Using OpenRouter

If you'd rather not install all three vendor CLIs, put an OpenRouter key in `~/.council/config.toml`:

```toml
[openrouter]
api_key = "sk-or-v1-..."

[openrouter.models]
claude = "anthropic/claude-sonnet-4.5"
gemini = "google/gemini-2.5-pro"
chatgpt = "openai/gpt-5"
```

Or export `OPENROUTER_API_KEY` in your shell (wins over the TOML file).

When a key is resolvable, all three elders go through OpenRouter and the vendor CLIs are not touched. After each round the TUI shows `[openrouter] round: $X · session: $X · credits remaining: $X`. Headless mode prints the equivalent line once after synthesis.

If no key is set, the council falls back to the existing vendor-CLI behaviour with no change.
````

Also soften line 8 of `README.md`:

Replace:

```
Send one prompt to Claude, Gemini, and ChatGPT simultaneously, watch them debate, and get one synthesised answer, all using your existing paid subscriptions (no API charges).
```

With:

```
Send one prompt to Claude, Gemini, and ChatGPT simultaneously, watch them debate, and get one synthesised answer. Use your existing paid vendor subscriptions by default, or route through OpenRouter with a single API key.
```

- [ ] **Step 2: Add "Using OpenRouter" section to `docs/USAGE.md`**

Append at the end of `docs/USAGE.md`:

```markdown
## Using OpenRouter

The council can route all three elders through [OpenRouter](https://openrouter.ai/) instead of the vendor CLIs. This is useful when you don't want to install and authenticate each vendor CLI separately, or when you're running the council in an environment (server, container) where those CLIs aren't available.

### Activation

OpenRouter mode turns on automatically when an API key is resolvable. The resolution order is:

1. `OPENROUTER_API_KEY` environment variable
2. `openrouter.api_key` in `~/.council/config.toml`

If neither source yields a non-empty string, the council uses the vendor CLIs as before.

### Config file

`~/.council/config.toml`:

```toml
[openrouter]
api_key = "sk-or-v1-..."

[openrouter.models]
claude = "anthropic/claude-sonnet-4.5"
gemini = "google/gemini-2.5-pro"
chatgpt = "openai/gpt-5"
```

OpenRouter model ids are namespaced as `provider/model`. See [OpenRouter's model list](https://openrouter.ai/models) for what's available.

### Model precedence (per elder)

Highest wins:

1. `--claude-model` / `--gemini-model` / `--codex-model` CLI flag
2. `COUNCIL_CLAUDE_MODEL` / `COUNCIL_GEMINI_MODEL` / `COUNCIL_CODEX_MODEL` env var
3. `[openrouter.models].<elder>` in `~/.council/config.toml`
4. Hard-coded default (`anthropic/claude-sonnet-4.5`, `google/gemini-2.5-pro`, `openai/gpt-5`)

Note: in OpenRouter mode the CLI flag and env var values are passed verbatim as OpenRouter model ids. A CLI-flavoured alias like `sonnet` will not resolve through OpenRouter — use the full OpenRouter id (`anthropic/claude-sonnet-4.5`) when that transport is active.

### Cost visibility

- **TUI:** after each round, a notice appears: `[openrouter] round: $X · session: $X · credits remaining: $X` (or `credits used: $X` for pay-as-you-go keys without a hard limit).
- **Headless:** a single summary line is printed after the synthesis.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/USAGE.md
git commit -m "docs: OpenRouter setup, precedence, and cost visibility"
```

---

## Final verification

- [ ] **Step 1: Full test suite passes**

Run: `pytest -v`
Expected: All non-integration tests PASS. Integration tests remain deselected (default config uses `-m 'not integration'`).

- [ ] **Step 2: Lint**

Run: `ruff check .`
Expected: No new warnings introduced by this plan's changes.

- [ ] **Step 3: Manual smoke — no-key path unchanged**

Run: `OPENROUTER_API_KEY= council --help`
Expected: Help prints exactly as before. No TOML / no env key → nothing has changed functionally for existing users.

- [ ] **Step 4: Manual smoke — OpenRouter path activates (if you have a key)**

Temporarily write a minimal `~/.council/config.toml`, then run:

```
council-headless "Say 'hi' only." --synthesizer claude
```

Expected: Three short answers followed by a synthesis, then the `[openrouter] total spent: $X ...` summary line.
