# OpenRouter as an Elder Transport — Design

**Date:** 2026-04-19
**Status:** Approved (pending implementation plan)

## Problem

The council today reaches each elder by shelling out to a vendor CLI (`claude`, `gemini`, `codex`). This has three practical limits:

1. **Environment setup.** Every machine needs all three CLIs installed and each one authenticated separately.
2. **Model reach.** Users are constrained to what each vendor CLI exposes (e.g. no direct access to `gpt-4o` via `codex`).
3. **Portability.** Running the council from a server, a container, or anywhere the vendor CLIs aren't available is awkward.

[OpenRouter](https://openrouter.ai/) exposes most major LLMs behind one HTTPS endpoint with a single API key. If the user has an OpenRouter key, we can serve all three elders through that one transport and drop the need for any vendor CLI.

## Goals

- Let the user configure OpenRouter once (API key + per-elder model) and have the council route all three elders through it.
- Preserve the existing CLI-based behaviour as the default when no OpenRouter key is configured — zero regression for current users.
- Surface OpenRouter spending in the UI so the user can see cost per session and remaining credit.
- Keep the domain core (`DebateService`, ports, events, models) untouched; add only at the adapter and app-wiring layers.

## Non-goals

- **Mixed transport.** No per-elder choice between CLI and OpenRouter. It's all-or-nothing per run, based on whether a key is resolved.
- **Streaming.** `ElderPort.ask()` still returns a full string. SSE streaming is deferred.
- **Cost budgeting / limits.** We show spend; we don't enforce caps.
- **Pack-level transport override.** Packs don't yet influence transport selection.
- **Migration of existing `--*-model` semantics.** Vendor-CLI model flags continue to mean what they mean today (CLI model alias); in OpenRouter mode they're passed verbatim as the OpenRouter model id — the user is responsible for using OpenRouter-flavoured ids when OpenRouter is active.

## Product decisions

| Decision | Choice |
|---|---|
| Activation | OpenRouter is used when an API key is resolvable from any source; otherwise the CLI adapters are used. |
| Key sources (highest wins) | `OPENROUTER_API_KEY` env var > `openrouter.api_key` in `~/.council/config.toml` |
| Model sources per elder (highest wins) | `--<elder>-model` CLI flag > `COUNCIL_<ELDER>_MODEL` env var > `[openrouter.models].<elder>` in TOML > hard-coded default |
| Hard-coded model defaults | `claude = anthropic/claude-sonnet-4.5`, `gemini = google/gemini-2.5-pro`, `chatgpt = openai/gpt-5` |
| Config format | TOML (`~/.council/config.toml`), read via stdlib `tomllib`. No new parsing dependency. |
| HTTP client | `httpx>=0.27` as a new runtime dependency. |
| Streaming | No. Non-streaming chat completion. |
| Health check | "API key present" → healthy. Reachability deferred to first `ask()`. |
| Error mapping | `401/403 → auth_failed`, `429 → quota_exhausted`, `httpx.TimeoutException → timeout`, malformed JSON → `unparseable`, other → `nonzero_exit`. |
| Cost tracking | Adapter captures `usage.cost` per response; exposes `session_cost_usd`, `session_tokens`, and `fetch_credits()`. |
| Cost surfacing (TUI) | After each `RoundCompleted`, write a line to the `#notices` area: `[openrouter] round: $X · session: $X` followed by `· credits remaining: $X` when the key has a known limit, or `· credits used: $X` otherwise. |
| Cost surfacing (headless) | After synthesis, print the same `[openrouter] round: $X · session: $X · credits remaining/used: $X` line as the TUI (one-shot, no per-round delta). |
| Empty env key (`OPENROUTER_API_KEY=`) | Treated as absent — does not activate OpenRouter mode. |
| Malformed TOML | Raise with a clear message at startup; do not fall back silently. |
| Unreadable TOML (permissions) | Log a warning on stderr, treat as absent. |

## Architecture fit

```
┌──────────────────────────┐     ┌──────────────────────────┐
│  council/app/tui/app.py  │     │ council/app/headless/    │
│          main()          │     │          main()          │
└────────────┬─────────────┘     └────────────┬─────────────┘
             │                                │
             └───────────────┬────────────────┘
                             ▼
              ┌──────────────────────────┐
              │ council/app/bootstrap.py │
              │      build_elders()      │
              └─────────────┬────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │  council/app/config.py   │
              │        load_config()     │
              └─────────────┬────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         │                                     │
         ▼                                     ▼
  key resolved                           no key
         │                                     │
         ▼                                     ▼
  OpenRouterAdapter × 3              SubprocessElder × 3
  (council/adapters/                 (unchanged today)
   elders/openrouter.py)
```

### Components

**`council/app/config.py` (new)**
- Pure, no network I/O. Reads `~/.council/config.toml` if present, merges with environment variables, and returns a frozen `AppConfig` dataclass:

  ```python
  @dataclass(frozen=True)
  class AppConfig:
      openrouter_api_key: str | None
      openrouter_models: dict[ElderId, str]   # empty dict if section absent
  ```

- Exposes a top-level `load_config(path: Path | None = None) -> AppConfig`. Default path is `~/.council/config.toml`. Path override is for tests.
- Missing file / missing section → empty values, not error.
- Unreadable file → log a `logging.warning` and treat as missing.
- Unparseable TOML → raise `tomllib.TOMLDecodeError` with the path prefixed to the message.
- Empty-string `OPENROUTER_API_KEY` is normalised to `None`.

**`council/adapters/elders/openrouter.py` (new)**
- Implements the `ElderPort` protocol (`ask`, `health_check`), same shape as `SubprocessElder`.
- Constructor: `OpenRouterAdapter(elder_id, model, api_key, *, client: httpx.AsyncClient | None = None)`. The optional `client` lets tests inject an `httpx.MockTransport`.
- `ask(prompt, *, timeout_s=45.0)`:
  - `POST https://openrouter.ai/api/v1/chat/completions`
  - Headers: `Authorization: Bearer <key>`, `Content-Type: application/json`, `HTTP-Referer: https://github.com/typingincolor/council-of-elders`, `X-Title: council-of-elders`.
  - Body: `{"model": <model>, "messages": [{"role": "user", "content": prompt}], "usage": {"include": true}}`.
  - On success: extract `choices[0].message.content`, capture `usage.cost` (may be missing for some providers) into `self.session_cost_usd`, accumulate `usage.prompt_tokens`/`completion_tokens` into `self.session_tokens`.
  - On failure: raise `OpenRouterError(kind, detail)` — a new exception class with `.kind: ErrorKind` and `.detail: str` attributes, matching the duck-typing already in `DebateService`.
- `health_check()`: return `True` if `api_key` is non-empty.
- `fetch_credits() -> tuple[float, float | None]`: `GET /api/v1/credits` returning `(used_usd, limit_usd_or_None)`. Swallows errors (returns best-effort; missing data → `(0.0, None)`) — credit display is advisory, not load-bearing.

**`council/app/bootstrap.py` (new)**
- Module-level constant `_DEFAULT_OPENROUTER_MODELS: dict[ElderId, str]` holding the hard-coded fallbacks from the product-decisions table.
- `build_elders(config: AppConfig, *, cli_models: dict[ElderId, str | None]) -> tuple[dict[ElderId, ElderPort], bool]` where the second return value is `True` when OpenRouter is active.
- `cli_models` is the resolved-from-CLI-flag value per elder (already-merged with `COUNCIL_*_MODEL` env — both entry points already do this).
- Logic:
  - If `config.openrouter_api_key` is set: for each elder, resolve model = `cli_models[e] or config.openrouter_models.get(e) or _DEFAULT_OPENROUTER_MODELS[e]`. Build three `OpenRouterAdapter`s.
  - Else: build the three `SubprocessElder` adapters as today, passing `cli_models[e]`.

### Data flow for a single `ask`

1. TUI or headless `main()` calls `load_config()`.
2. `build_elders(config, cli_models=...)` produces the elder dict.
3. The rest of the app is untouched. `DebateService` calls `elder.ask(prompt)` on whichever port it was handed.
4. For OpenRouter, `ask()` updates `session_cost_usd` as a side effect and returns the message text.
5. TUI consumes `RoundCompleted`; if it's holding `OpenRouterAdapter`s, it sums `session_cost_usd` across the three and writes a notice. Headless does the same once, after synthesis.

### Error paths

| Condition | Raised | Surfaces as |
|---|---|---|
| HTTP 401, 403 | `OpenRouterError("auth_failed", body-tail)` | `ElderAnswer` with `error.kind="auth_failed"` |
| HTTP 429 | `OpenRouterError("quota_exhausted", body-tail)` | `quota_exhausted` |
| Other 4xx, 5xx | `OpenRouterError("nonzero_exit", f"HTTP {status}: {body-tail}")` | `nonzero_exit` |
| `httpx.TimeoutException` | re-raised as `OpenRouterError("timeout", ...)` | `timeout` |
| JSON missing `choices[0].message.content` | `OpenRouterError("unparseable", ...)` | `unparseable` |
| Network error (DNS, refused, TLS) | `OpenRouterError("nonzero_exit", ...)` | `nonzero_exit` |

`DebateService` duck-types on `.kind` / `.detail`, so no change is needed there.

## Testing

- `tests/unit/test_config_loader.py` — precedence (env > TOML for key, CLI > env > TOML > default for models), missing file OK, empty env value treated as absent, malformed TOML raises, unreadable TOML warns and falls back.
- `tests/unit/test_openrouter_adapter.py` — using `httpx.MockTransport`:
  - Success parsing: body shape, headers, `usage.cost` captured into `session_cost_usd`.
  - Error mapping for 401, 403, 429, 500, timeout, malformed JSON, network error.
  - `fetch_credits()` happy path and error swallowing.
- `tests/unit/test_bootstrap.py` — OpenRouter branch vs. subprocess branch; model precedence end-to-end.
- `tests/contract/test_elder_port_contract.py` — extend so `OpenRouterAdapter` (with a `MockTransport`) is exercised alongside the subprocess adapters; contract equivalence verified.
- `tests/integration/test_openrouter_smoke.py` — `@pytest.mark.integration`, skipped unless `OPENROUTER_API_KEY` is set. Single round-trip against the real API using a cheap model.

## Docs

- `README.md`: add a short "Using OpenRouter" subsection under Quick start. Example `~/.council/config.toml`. Soften the "no API charges" pitch to "use your paid vendor subscriptions by default; or route through OpenRouter with a single API key."
- `docs/USAGE.md`: full "Using OpenRouter" section covering precedence, defaults, cost display, and OpenRouter-native model id convention (`provider/model`).

## Open risks

- **OpenRouter cost field availability.** `usage.cost` is populated by OpenRouter for most providers but isn't universally guaranteed. Design tolerates missing values (treat as `0.0` contribution to the session total, display `$?` where unknown). Not a blocker.
- **Credits endpoint format drift.** `/api/v1/credits` is a lightly-documented endpoint; shape may change. The adapter isolates the parsing in `fetch_credits()` and swallows errors so a breaking response change degrades gracefully to "credits unknown".
- **Vendor model naming confusion.** Users may pass `--claude-model sonnet` (a CLI alias) while OpenRouter is active, and get a 4xx from OpenRouter. Documented; not otherwise mitigated.
