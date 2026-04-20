# Diversity Engine Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refocus Council of Elders from a debate orchestrator into a diversity engine with adaptive interaction. Make roster diversity visible, adapt debate depth to diversity, preserve disagreement in the deliverable, and treat best-R1 as a mandatory baseline.

**Architecture:** Five sequential stages, each shippable alone. (1) diversity primitive + roster promotion to domain; (2) LLM-judged best-R1 baseline always surfaced alongside synthesis; (3) adaptive policy that consumes diversity and picks best-R1-first / single-critique / full-debate pipelines; (4) Answer/Why/Disagreements structured synthesis output; (5) convergence reframed as non-goal, per-run observability summary, model-vs-role experiment scaffold, judge-swap replication scaffold.

**Tech Stack:** Python 3.12, existing deps only (`httpx`, `pytest`, `pytest-asyncio`). No new runtime deps.

**Out of scope (deferred):** task-specific rosters, TUI changes (headless-first), empirical-calibration diversity scoring (tier-2; tier-1 heuristic ships first), automatic policy override, deterministic-rule disagreement detector.

**Evidence basis:** `docs/experiments/2026-04-19-9288-homogenisation.md` (n=8, one judge — directional). Architecture proceeds in parallel with replication on GPT-5 and Sonnet judges; the judge-swap infrastructure is scaffolded in Stage 5 but not a gate on Stages 1-4.

---

## File structure

**New domain modules:**
- `council/domain/roster.py` — `RosterSpec` dataclass (promoted from `council/experiments/homogenisation/rosters.py`)
- `council/domain/diversity.py` — `DiversityScore`, `score_roster()`, provider/family lookup
- `council/domain/best_r1.py` — `BestR1Selector` protocol + `LLMJudgedBestR1Selector` (consumes existing `judge_best_r1` rubric)
- `council/domain/debate_policy.py` — `DebatePolicy` dataclass + `policy_for(DiversityScore, user_override)`
- `council/domain/synthesis_output.py` — `SynthesisOutput` dataclass + parser for Answer/Why/Disagreements structure

**Modified:**
- `council/domain/models.py` — add `best_r1_elder`, `diversity_score` fields to `Debate`; `SynthesisOutput` replaces bare text on synthesis
- `council/domain/debate_service.py` — consume policy; stop-on-convergence becomes "stop when policy budget spent"
- `council/domain/prompting.py` — synthesis prompt rewritten to emit Answer/Why/Disagreements
- `council/domain/reporting.py` — consume `SynthesisOutput`; disagreements surfaced in user-facing output, not only audit
- `council/app/bootstrap.py` — return `(elders, using_openrouter, roster_spec)` — third element exposes what was wired
- `council/app/headless/main.py` — compute diversity, choose policy, run pipeline, emit structured output
- `council/experiments/homogenisation/rosters.py` — re-export `RosterSpec` from domain
- `docs/USAGE.md` — document diversity scoring, best-R1 baseline, adaptive policy
- `README.md` — reframe positioning (keep name, reframe description)

**New tests (unit):**
- `tests/unit/test_roster.py`, `test_diversity.py`, `test_best_r1.py`, `test_debate_policy.py`, `test_synthesis_output.py`

**New tests (e2e):**
- `tests/e2e/test_headless_best_r1_baseline.py`, `test_headless_low_diversity_warning.py`

**New experiments:**
- `council/experiments/diversity_split/` — 2×2 model × role matrix
- `scripts/judge_replication.py` — re-runs the homogenisation scorer with alternative judges (GPT-5, Sonnet)

---

## Shared types (referenced across stages)

```python
# council/domain/roster.py
@dataclass(frozen=True)
class RosterSpec:
    name: str
    models: dict[ElderId, str]  # e.g. {"claude": "anthropic/claude-sonnet-4.5", ...}

# council/domain/diversity.py
DiversityClass = Literal["low", "medium", "high"]

@dataclass(frozen=True)
class DiversityScore:
    classification: DiversityClass
    provider_count: int          # distinct providers (anthropic, google, openai, meta, ...)
    identical_model_count: int   # how many slots share the same model string
    flags: tuple[str, ...]        # e.g. "identical_models", "same_provider_trio", "unsafe_consensus_risk"
    rationale: str                # short human-readable reason

# council/domain/debate_policy.py
PolicyMode = Literal["best_r1_only", "single_critique", "full_debate"]

@dataclass(frozen=True)
class DebatePolicy:
    mode: PolicyMode
    max_rounds: int               # 1, 3, or 6 for best_r1_only / single_critique / full_debate
    synthesise: bool              # false iff best_r1_only wins by preference
    always_compute_best_r1: bool  # always true under the new direction
    warning: str | None           # e.g. "Low-diversity roster — degrading to best-R1-first."

# council/domain/best_r1.py
@dataclass(frozen=True)
class BestR1Selection:
    elder: ElderId
    reason: str
    raw: str  # judge response

class BestR1Selector(Protocol):
    async def select(self, debate: Debate) -> BestR1Selection: ...

# council/domain/synthesis_output.py
@dataclass(frozen=True)
class SynthesisOutput:
    answer: str
    why: str
    disagreements: tuple[str, ...]  # may be empty
    raw: str                         # full model output
```

---

## Stage 1 — Diversity primitive + roster in domain

**Deliverable:** Call `score_roster(roster_spec)` → `DiversityScore`. `RosterSpec` is a domain type used by both app and experiments.

### Task 1.1 — Create `RosterSpec` in the domain layer

**Files:**
- Create: `council/domain/roster.py`
- Create: `tests/unit/test_roster.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_roster.py
from council.domain.roster import RosterSpec


def test_roster_spec_is_a_frozen_dataclass_with_name_and_models():
    spec = RosterSpec(
        name="mixed",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        },
    )
    assert spec.name == "mixed"
    assert spec.models["claude"] == "anthropic/claude-sonnet-4.5"


def test_roster_spec_is_immutable():
    import dataclasses

    spec = RosterSpec(name="n", models={"claude": "m"})  # type: ignore[typeddict-item]
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        spec.name = "other"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_roster.py -v`
Expected: `ModuleNotFoundError: No module named 'council.domain.roster'`

- [ ] **Step 3: Write the module**

```python
# council/domain/roster.py
"""Domain-level roster specification.

Represents the (slot → model-id) mapping for a council, promoted from
council/experiments/homogenisation/rosters.py so the main app and
experiments share the same type.
"""
from __future__ import annotations

from dataclasses import dataclass

from council.domain.models import ElderId


@dataclass(frozen=True)
class RosterSpec:
    name: str
    models: dict[ElderId, str]
```

- [ ] **Step 4: Re-export from experiments for backwards compat**

Edit `council/experiments/homogenisation/rosters.py`: replace the local `RosterSpec` dataclass with `from council.domain.roster import RosterSpec` at the top; delete the in-file dataclass definition (lines 20-23). Leave `ROSTERS` tuple and `build_roster_elders` unchanged.

- [ ] **Step 5: Run all roster-touching tests**

Run: `pytest tests/unit/test_roster.py tests/unit/test_homogenisation_rosters.py tests/unit/test_homogenisation_runner.py tests/unit/test_homogenisation_scorer.py -v`
Expected: PASS (backwards-compat re-export works).

- [ ] **Step 6: Commit**

```bash
git add council/domain/roster.py council/experiments/homogenisation/rosters.py tests/unit/test_roster.py
git commit -m "refactor(domain): promote RosterSpec into the domain layer"
```

---

### Task 1.2 — Provider/family lookup table

**Files:**
- Create: `council/domain/diversity.py`
- Create: `tests/unit/test_diversity.py`

- [ ] **Step 1: Write the failing test for provider extraction**

```python
# tests/unit/test_diversity.py
from council.domain.diversity import provider_of


class TestProviderOf:
    def test_anthropic_prefix(self):
        assert provider_of("anthropic/claude-sonnet-4.5") == "anthropic"

    def test_openai_prefix(self):
        assert provider_of("openai/gpt-5") == "openai"

    def test_google_prefix(self):
        assert provider_of("google/gemini-2.5-pro") == "google"

    def test_meta_prefix(self):
        assert provider_of("meta-llama/llama-3.1-70b-instruct") == "meta-llama"

    def test_unknown_prefix_returns_prefix_verbatim(self):
        # Future-proof: unknown providers still contribute to distinct count.
        assert provider_of("novaco/frontier-2") == "novaco"

    def test_bare_model_id_returns_unknown(self):
        # A vendor-CLI alias like "sonnet" (no slash) has no provider.
        assert provider_of("sonnet") == "unknown"
```

- [ ] **Step 2: Run it — verify it fails**

Run: `pytest tests/unit/test_diversity.py -v`
Expected: `ModuleNotFoundError: No module named 'council.domain.diversity'`

- [ ] **Step 3: Write minimal implementation**

```python
# council/domain/diversity.py
"""Diversity scoring for a council roster.

Tier-1 heuristic: provider distinctness plus identical-model penalty.
Provider is inferred from the OpenRouter model-id prefix. Vendor-CLI
aliases (no slash, e.g. "sonnet") count as "unknown" — the heuristic
is only meaningful when OpenRouter is in use.

This is a hypothesis-grade score; calibrate against the homogenisation
probe before over-trusting it. See
docs/experiments/2026-04-19-9288-homogenisation.md.
"""
from __future__ import annotations


def provider_of(model_id: str) -> str:
    if "/" not in model_id:
        return "unknown"
    return model_id.split("/", 1)[0]
```

- [ ] **Step 4: Run and verify**

Run: `pytest tests/unit/test_diversity.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/domain/diversity.py tests/unit/test_diversity.py
git commit -m "feat(diversity): add provider_of() primitive"
```

---

### Task 1.3 — `score_roster()` returns classification + flags

**Files:**
- Modify: `council/domain/diversity.py`
- Modify: `tests/unit/test_diversity.py`

Thresholds:
- `high`: 3 distinct providers AND no identical model strings.
- `medium`: 2 distinct providers, or 3 distinct providers with one identical-model pair.
- `low`: 1 distinct provider, OR all three models identical.

Flags (any may apply):
- `identical_models` — two or more slots share the same model string.
- `same_provider_trio` — all three slots share a provider.
- `unsafe_consensus_risk` — set on `low` classification.
- `mixed_lineage_risk` — set when medium and the open-weights slot is absent (heuristic: no meta-llama/mistralai/deepseek provider). For tier-1 it's informational only.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_diversity.py  (append)
from council.domain.diversity import DiversityScore, score_roster
from council.domain.roster import RosterSpec


def _spec(**models):
    return RosterSpec(name="t", models=models)


class TestScoreRoster:
    def test_three_distinct_providers_no_identical_is_high(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="google/gemini-2.5-pro",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "high"
        assert s.provider_count == 3
        assert s.identical_model_count == 0

    def test_open_weights_substitute_is_high(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="meta-llama/llama-3.1-70b-instruct",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "high"

    def test_all_three_identical_models_is_low(self):
        spec = _spec(
            claude="openai/gpt-5-mini",
            gemini="openai/gpt-5-mini",
            chatgpt="openai/gpt-5-mini",
        )
        s = score_roster(spec)
        assert s.classification == "low"
        assert "identical_models" in s.flags
        assert "same_provider_trio" in s.flags
        assert "unsafe_consensus_risk" in s.flags

    def test_same_provider_different_scale_is_medium(self):
        spec = _spec(
            claude="anthropic/claude-opus-4.5",
            gemini="anthropic/claude-haiku-4.5",
            chatgpt="anthropic/claude-sonnet-4.5",
        )
        s = score_roster(spec)
        assert s.classification == "medium"
        assert "same_provider_trio" in s.flags
        assert "identical_models" not in s.flags

    def test_two_providers_no_identical_is_medium(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="anthropic/claude-haiku-4.5",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "medium"

    def test_three_providers_but_two_identical_strings_is_medium(self):
        # Pathological — same-provider same-model twice + one different provider.
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="anthropic/claude-sonnet-4.5",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "medium"
        assert "identical_models" in s.flags

    def test_rationale_is_non_empty(self):
        s = score_roster(
            _spec(
                claude="openai/gpt-5-mini",
                gemini="openai/gpt-5-mini",
                chatgpt="openai/gpt-5-mini",
            )
        )
        assert s.rationale  # non-empty human-readable string
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/unit/test_diversity.py -v`
Expected: FAIL (score_roster / DiversityScore not defined).

- [ ] **Step 3: Implement**

Append to `council/domain/diversity.py`:

```python
from dataclasses import dataclass
from typing import Literal

from council.domain.roster import RosterSpec

DiversityClass = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class DiversityScore:
    classification: DiversityClass
    provider_count: int
    identical_model_count: int
    flags: tuple[str, ...]
    rationale: str


def score_roster(spec: RosterSpec) -> DiversityScore:
    models = list(spec.models.values())
    providers = {provider_of(m) for m in models}
    provider_count = len(providers)
    # Count model-string collisions: how many slots share a model with at least one other.
    identical_model_count = sum(1 for m in models if models.count(m) > 1)
    all_identical = len(set(models)) == 1

    flags: list[str] = []
    if identical_model_count >= 2:
        flags.append("identical_models")
    if provider_count == 1:
        flags.append("same_provider_trio")

    if all_identical or provider_count == 1:
        classification: DiversityClass = "low"
        flags.append("unsafe_consensus_risk")
        rationale = (
            f"{provider_count} distinct provider(s); all three slots use the same provider family. "
            "Debate will iterate over a single perspective — prefer best-R1-first."
        )
    elif provider_count == 3 and identical_model_count == 0:
        classification = "high"
        rationale = "Three distinct providers, no slot collisions — full debate is justified."
    else:
        classification = "medium"
        bits: list[str] = []
        if provider_count == 2:
            bits.append("two distinct providers")
        if provider_count == 3 and identical_model_count >= 2:
            bits.append("three providers but duplicated model strings")
        if provider_count == 1:  # already handled, but defensive
            bits.append("single provider")
        rationale = "; ".join(bits) + " — single critique round likely enough."

    return DiversityScore(
        classification=classification,
        provider_count=provider_count,
        identical_model_count=identical_model_count,
        flags=tuple(flags),
        rationale=rationale,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_diversity.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/domain/diversity.py tests/unit/test_diversity.py
git commit -m "feat(diversity): score_roster() classifies low/medium/high with flags"
```

---

### Task 1.4 — Wire roster+diversity through bootstrap

**Files:**
- Modify: `council/app/bootstrap.py`
- Modify: `tests/unit/test_bootstrap.py`

Change `build_elders()` to also return a `RosterSpec` reflecting what was wired. Subprocess branch returns a sentinel spec (`name="subprocess"`, models empty) because we don't know model IDs reliably when using vendor CLIs.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_bootstrap.py  (append at end)
from council.domain.roster import RosterSpec


class TestRosterSpecReturned:
    def test_openrouter_branch_returns_real_spec(self):
        cfg = AppConfig(openrouter_api_key="sk-or-x", openrouter_models={})
        elders, using_or, spec = build_elders(
            cfg, cli_models={"claude": None, "gemini": None, "chatgpt": None}
        )
        assert using_or is True
        assert isinstance(spec, RosterSpec)
        assert spec.name == "openrouter"
        assert spec.models["claude"] == "anthropic/claude-sonnet-4.5"
        assert spec.models["gemini"] == "meta-llama/llama-3.1-70b-instruct"
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
```

- [ ] **Step 2: Run tests — verify fail**

Run: `pytest tests/unit/test_bootstrap.py -v`
Expected: FAIL — `build_elders` currently returns 2-tuple.

- [ ] **Step 3: Update `build_elders`**

Edit `council/app/bootstrap.py`:

```python
from council.domain.roster import RosterSpec

def build_elders(
    config: AppConfig,
    *,
    cli_models: dict[ElderId, str | None],
) -> tuple[dict[ElderId, ElderPort], bool, RosterSpec]:
    if config.openrouter_api_key:
        elders: dict[ElderId, ElderPort] = {}
        resolved_models: dict[ElderId, str] = {}
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
            resolved_models[eid] = model
        return elders, True, RosterSpec(name="openrouter", models=resolved_models)

    elders = {
        "claude": ClaudeCodeAdapter(model=cli_models.get("claude")),
        "gemini": GeminiCLIAdapter(model=cli_models.get("gemini")),
        "chatgpt": CodexCLIAdapter(model=cli_models.get("chatgpt")),
    }
    return elders, False, RosterSpec(name="subprocess", models={})
```

- [ ] **Step 4: Update call sites (2-tuple → 3-tuple)**

Touch `council/app/headless/main.py` and `council/app/tui/app.py`. Each has a line `elders, using_openrouter = build_elders(...)`. Replace with `elders, using_openrouter, roster_spec = build_elders(...)`. For this task, do NOT yet use `roster_spec` — Stage 3 consumes it.

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/app/bootstrap.py council/app/headless/main.py council/app/tui/app.py tests/unit/test_bootstrap.py
git commit -m "refactor(bootstrap): return RosterSpec alongside elders"
```

---

## Stage 2 — Best-R1 baseline (LLM-judged)

**Deliverable:** After R1 (and only R1), whenever OpenRouter is configured, compute best-R1 using the existing judge rubric and record it on the debate. The headless output surfaces best-R1 alongside synthesis with a clear label for the judge's preferred answer.

### Task 2.1 — Promote `judge_best_r1` rubric + selector into the domain layer

**Files:**
- Create: `council/domain/best_r1.py`
- Create: `tests/unit/test_best_r1.py`
- Modify: `council/experiments/homogenisation/judges.py` (re-export from domain)

- [ ] **Step 1: Failing test — `LLMJudgedBestR1Selector` calls the judge with three R1 texts and records the winner**

```python
# tests/unit/test_best_r1.py
import pytest

from datetime import datetime, timezone

from council.adapters.elders.fake import FakeElder
from council.domain.best_r1 import BestR1Selection, LLMJudgedBestR1Selector
from council.domain.models import CouncilPack, Debate, ElderAnswer, Round, Turn


def _ans(elder, text):
    return ElderAnswer(
        elder=elder, text=text, error=None, agreed=None,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


def _debate_with_r1():
    r1 = Round(
        number=1,
        turns=[
            Turn(elder="claude", answer=_ans("claude", "Claude R1 answer.")),
            Turn(elder="gemini", answer=_ans("gemini", "Gemini R1 answer.")),
            Turn(elder="chatgpt", answer=_ans("chatgpt", "ChatGPT R1 answer.")),
        ],
    )
    return Debate(
        id="t", prompt="What?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[r1], status="in_progress", synthesis=None,
    )


async def test_selector_returns_elder_from_judge_reply():
    judge = FakeElder(elder_id="claude", replies=["best: 2\nreason: Gemini strongest.\n"])
    selector = LLMJudgedBestR1Selector(judge_port=judge)
    pick = await selector.select(_debate_with_r1())
    assert isinstance(pick, BestR1Selection)
    assert pick.elder == "gemini"
    assert "Gemini" in pick.reason


async def test_selector_returns_none_when_no_r1():
    judge = FakeElder(elder_id="claude", replies=["best: 1\nreason: x\n"])
    selector = LLMJudgedBestR1Selector(judge_port=judge)
    empty = Debate(
        id="t", prompt="x",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[], status="in_progress", synthesis=None,
    )
    assert await selector.select(empty) is None
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/unit/test_best_r1.py -v`
Expected: `ModuleNotFoundError` for `council.domain.best_r1`.

- [ ] **Step 3: Implement — move rubric prompt + parser into the domain, wrap as a selector**

```python
# council/domain/best_r1.py
"""Best-R1 selection — LLM-judged.

Factored out of council/experiments/homogenisation/judges.py so the
production headless pipeline (not just experiments) can use it. Best-R1
is a mandatory baseline under the diversity-engine direction:
docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from council.domain.models import Debate, ElderId, Message
from council.domain.ports import ElderPort

_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("claude", "gemini", "chatgpt")

BEST_R1_PROMPT = """You will see three candidate answers to the user's question. Pick the single strongest one on correctness, completeness, and shape-fit. Ignore stylistic polish. Do not favour longer answers.

User's question:
<<<
{question}
>>>

Answer 1:
<<<
{answer_1}
>>>

Answer 2:
<<<
{answer_2}
>>>

Answer 3:
<<<
{answer_3}
>>>

Emit EXACTLY:
best: 1 | 2 | 3
reason: one sentence."""

_BEST_RE = re.compile(r"^\s*best\s*:\s*([1-3])\b", re.MULTILINE | re.IGNORECASE)
_REASON_RE = re.compile(r"^\s*reason\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class BestR1Selection:
    elder: ElderId
    reason: str
    raw: str


class BestR1Selector(Protocol):
    async def select(self, debate: Debate) -> BestR1Selection | None: ...


@dataclass
class LLMJudgedBestR1Selector:
    judge_port: ElderPort

    async def select(self, debate: Debate) -> BestR1Selection | None:
        if not debate.rounds:
            return None
        r1 = debate.rounds[0]
        by_elder = {t.elder: (t.answer.text or "") for t in r1.turns}
        answers = tuple(by_elder.get(e, "") for e in _ELDER_ORDER)
        if not any(a.strip() for a in answers):
            return None
        prompt = BEST_R1_PROMPT.format(
            question=debate.prompt.strip(),
            answer_1=answers[0].strip(),
            answer_2=answers[1].strip(),
            answer_3=answers[2].strip(),
        )
        raw = await self.judge_port.ask([Message("user", prompt)])
        cleaned = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip(), flags=re.MULTILINE)
        best_m = _BEST_RE.search(cleaned)
        reason_m = _REASON_RE.search(cleaned)
        best_idx = int(best_m.group(1)) - 1 if best_m else 0
        best_idx = max(0, min(2, best_idx))
        return BestR1Selection(
            elder=_ELDER_ORDER[best_idx],
            reason=reason_m.group(1).strip() if reason_m else "",
            raw=raw,
        )
```

- [ ] **Step 4: Re-export from the experiments judges module to keep existing callers working**

Edit `council/experiments/homogenisation/judges.py`: replace the `BEST_R1_PROMPT` / `BestR1Observation` / `judge_best_r1` block (roughly lines 107-156 and 247-258) with a thin wrapper that calls the new domain selector. Simplest: keep the old `judge_best_r1` coroutine function, but delegate to `LLMJudgedBestR1Selector` internally so existing experiment code keeps passing.

Specifically replace the old `_parse_best_r1` / `judge_best_r1` definitions with:

```python
from council.domain.best_r1 import (
    BEST_R1_PROMPT,
    BestR1Selection,
    LLMJudgedBestR1Selector,
)


@dataclass(frozen=True)
class BestR1Observation:
    best_index: int
    reason: str
    raw: str


async def judge_best_r1(
    *, question: str, answers: tuple[str, str, str], judge_port: ElderPort
) -> BestR1Observation:
    # Kept for the experiments module; delegates to the domain selector
    # via a minimal fake debate. Existing tests expect best_index ∈ {1,2,3}.
    from datetime import datetime, timezone
    from council.domain.models import CouncilPack, Debate, ElderAnswer, Round, Turn

    def _ans(eid, txt):
        return ElderAnswer(
            elder=eid, text=txt, error=None, agreed=None,
            created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        )

    debate = Debate(
        id="t", prompt=question,
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[Round(number=1, turns=[
            Turn(elder="claude", answer=_ans("claude", answers[0])),
            Turn(elder="gemini", answer=_ans("gemini", answers[1])),
            Turn(elder="chatgpt", answer=_ans("chatgpt", answers[2])),
        ])],
        status="in_progress", synthesis=None,
    )
    sel = await LLMJudgedBestR1Selector(judge_port=judge_port).select(debate)
    assert sel is not None
    idx = {"claude": 1, "gemini": 2, "chatgpt": 3}[sel.elder]
    return BestR1Observation(best_index=idx, reason=sel.reason, raw=sel.raw)
```

- [ ] **Step 5: Run both unit test suites**

Run: `pytest tests/unit/test_best_r1.py tests/unit/test_homogenisation_judges.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/domain/best_r1.py council/experiments/homogenisation/judges.py tests/unit/test_best_r1.py
git commit -m "feat(domain): promote best-R1 selector into domain layer"
```

---

### Task 2.2 — Record best-R1 on the `Debate` model

**Files:**
- Modify: `council/domain/models.py`
- Modify: `tests/unit/test_models.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_models.py  (append)
def test_debate_has_best_r1_elder_field_defaulting_to_none():
    from council.domain.models import CouncilPack, Debate

    d = Debate(
        id="x", prompt="y",
        pack=CouncilPack(name="p", shared_context=None, personas={}),
        rounds=[], status="in_progress", synthesis=None,
    )
    assert d.best_r1_elder is None
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/unit/test_models.py -v`
Expected: FAIL — `best_r1_elder` doesn't exist.

- [ ] **Step 3: Add the field**

In `council/domain/models.py`, extend the `Debate` dataclass:

```python
@dataclass
class Debate:
    id: str
    prompt: str
    pack: CouncilPack
    rounds: list[Round]
    status: DebateStatus
    synthesis: ElderAnswer | None
    user_messages: list[UserMessage] = field(default_factory=list)
    best_r1_elder: ElderId | None = None
```

- [ ] **Step 4: Run**

Run: `pytest tests/unit/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Update `JsonFileStore` serialization**

Check `council/adapters/storage/json_file.py` — if it serialises `Debate` field-by-field, add `best_r1_elder` to the serialise + deserialise paths. If it uses `dataclasses.asdict`, no change needed, but the reader must handle old files missing the key (`data.get("best_r1_elder")`).

Run: `pytest tests/unit/test_json_file_store.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add council/domain/models.py council/adapters/storage/json_file.py tests/unit/test_models.py
git commit -m "feat(models): add best_r1_elder to Debate"
```

---

### Task 2.3 — Compute best-R1 in the headless pipeline

**Files:**
- Modify: `council/app/headless/main.py`
- Create: `tests/e2e/test_headless_best_r1_baseline.py`

The rule: when OpenRouter is configured (`using_openrouter is True`), construct a judge port pointing at a cheap model (`google/gemini-2.5-flash`, same default used by `council-analyze`) and call `LLMJudgedBestR1Selector` after R1 completes. Record the elder on `debate.best_r1_elder`. Print a line: `Best R1 (judge-picked): <Elder> — <reason>`.

When using the subprocess branch, skip best-R1 computation; print `Best-R1 baseline unavailable (no OpenRouter key configured).`

- [ ] **Step 1: Failing e2e test**

```python
# tests/e2e/test_headless_best_r1_baseline.py
from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.models import CouncilPack


async def test_headless_prints_best_r1_selection_when_judge_available(capsys):
    elders = {
        "claude": FakeElder(elder_id="claude", replies=[
            "R1 Claude", "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
            "R3 Claude\nCONVERGED: yes", "Final synth.",
        ]),
        "gemini": FakeElder(elder_id="gemini", replies=[
            "R1 Gemini", "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
            "R3 Gemini\nCONVERGED: yes",
        ]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=[
            "R1 ChatGPT", "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
            "R3 ChatGPT\nCONVERGED: yes",
        ]),
    }
    # Inject a judge via the new kwarg.
    judge = FakeElder(elder_id="claude", replies=["best: 2\nreason: clearest.\n"])
    await run_headless(
        prompt="What should I do?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
        synthesizer="claude",
        best_r1_judge=judge,  # new param
    )
    out = capsys.readouterr().out
    assert "Best R1 (judge-picked): Gemini" in out
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/e2e/test_headless_best_r1_baseline.py -v`
Expected: FAIL — `best_r1_judge` kwarg unsupported.

- [ ] **Step 3: Add the kwarg and plumbing to `run_headless`**

In `council/app/headless/main.py`, add `best_r1_judge: ElderPort | None = None` to `run_headless`. After R1 completes (or after the last round, doesn't matter — R1 is already preserved), call the selector:

```python
from council.domain.best_r1 import LLMJudgedBestR1Selector

# ... after await svc.run_round(debate)  # R1
if best_r1_judge is not None:
    selector = LLMJudgedBestR1Selector(judge_port=best_r1_judge)
    pick = await selector.select(debate)
    if pick is not None:
        debate.best_r1_elder = pick.elder
        print(f"Best R1 (judge-picked): {_LABELS[pick.elder]} — {pick.reason}")
else:
    print("Best-R1 baseline unavailable (no OpenRouter key configured).")
```

Place the print AFTER the per-round printing loop so the line lands near the synthesis output, not in the middle of the transcript.

- [ ] **Step 4: Wire a real judge in `main()`**

In `main()` (the CLI entry), after `elders, using_openrouter, _ = build_elders(...)` add:

```python
best_r1_judge: ElderPort | None = None
if using_openrouter and config.openrouter_api_key:
    from council.adapters.elders.openrouter import OpenRouterAdapter
    best_r1_judge = OpenRouterAdapter(
        elder_id="claude",
        model="google/gemini-2.5-flash",
        api_key=config.openrouter_api_key,
    )
```

Pass through to `run_headless(..., best_r1_judge=best_r1_judge)`.

- [ ] **Step 5: Run**

Run: `pytest tests/e2e/test_headless_best_r1_baseline.py tests/e2e/test_headless_flow.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/app/headless/main.py tests/e2e/test_headless_best_r1_baseline.py
git commit -m "feat(headless): compute judge-picked best-R1 baseline alongside synthesis"
```

---

## Stage 3 — Adaptive debate policy

**Deliverable:** Before the debate runs, headless computes a `DebatePolicy` from the roster's diversity score. Low diversity prints a warning and uses the best-R1-first pipeline (R1 only, no synthesis unless a separate preference judge says it beats best-R1). Medium runs R1 + one critique round + synthesis. High runs full debate + synthesis. `--policy` CLI override skips the computation.

### Task 3.1 — `DebatePolicy` dataclass + `policy_for`

**Files:**
- Create: `council/domain/debate_policy.py`
- Create: `tests/unit/test_debate_policy.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_debate_policy.py
from council.domain.debate_policy import DebatePolicy, policy_for
from council.domain.diversity import DiversityScore


def _score(cls, flags=()):
    return DiversityScore(
        classification=cls, provider_count=3 if cls == "high" else 1,
        identical_model_count=0, flags=flags, rationale="t",
    )


class TestPolicyFor:
    def test_low_diversity_picks_best_r1_only(self):
        p = policy_for(_score("low", ("unsafe_consensus_risk",)))
        assert p.mode == "best_r1_only"
        assert p.max_rounds == 1
        assert p.synthesise is False
        assert p.always_compute_best_r1 is True
        assert p.warning and "low-diversity" in p.warning.lower()

    def test_medium_diversity_picks_single_critique(self):
        p = policy_for(_score("medium"))
        assert p.mode == "single_critique"
        assert p.max_rounds == 2  # R1 + one critique
        assert p.synthesise is True
        assert p.warning is None

    def test_high_diversity_picks_full_debate(self):
        p = policy_for(_score("high"))
        assert p.mode == "full_debate"
        assert p.max_rounds >= 3
        assert p.synthesise is True
        assert p.warning is None

    def test_user_override_wins(self):
        override = DebatePolicy(
            mode="full_debate", max_rounds=6,
            synthesise=True, always_compute_best_r1=True, warning=None,
        )
        p = policy_for(_score("low"), user_override=override)
        assert p is override
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/unit/test_debate_policy.py -v`
Expected: `ModuleNotFoundError: council.domain.debate_policy`.

- [ ] **Step 3: Implement**

```python
# council/domain/debate_policy.py
"""Adaptive debate policy — maps a DiversityScore to a pipeline choice.

Low diversity → best-R1-first (skip debate). Medium → R1 + one critique
round + synthesis. High → full debate + synthesis. Always compute
best-R1 when a judge is available (mandatory baseline).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from council.domain.diversity import DiversityScore

PolicyMode = Literal["best_r1_only", "single_critique", "full_debate"]


@dataclass(frozen=True)
class DebatePolicy:
    mode: PolicyMode
    max_rounds: int
    synthesise: bool
    always_compute_best_r1: bool
    warning: str | None


def policy_for(
    diversity: DiversityScore, *, user_override: DebatePolicy | None = None
) -> DebatePolicy:
    if user_override is not None:
        return user_override

    if diversity.classification == "low":
        return DebatePolicy(
            mode="best_r1_only",
            max_rounds=1,
            synthesise=False,
            always_compute_best_r1=True,
            warning=(
                "Low-diversity roster detected — degrading to best-R1-first. "
                f"Reason: {diversity.rationale}"
            ),
        )
    if diversity.classification == "medium":
        return DebatePolicy(
            mode="single_critique",
            max_rounds=2,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
    return DebatePolicy(
        mode="full_debate",
        max_rounds=6,
        synthesise=True,
        always_compute_best_r1=True,
        warning=None,
    )
```

- [ ] **Step 4: Run**

Run: `pytest tests/unit/test_debate_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/domain/debate_policy.py tests/unit/test_debate_policy.py
git commit -m "feat(policy): adaptive debate policy from diversity score"
```

---

### Task 3.2 — Consume policy in headless pipeline

**Files:**
- Modify: `council/app/headless/main.py`
- Create: `tests/e2e/test_headless_low_diversity_warning.py`
- Modify: `tests/e2e/test_headless_flow.py` (existing tests should still pass — they use `max_rounds=3` default, which is fine)

Pipeline behaviour by mode:
- `best_r1_only`: run only R1, compute best-R1, do not run R2, do not synthesise. Print best-R1 text as the answer along with the warning.
- `single_critique`: run R1 + R2 (which is cross-exam), skip R3+, synthesise.
- `full_debate`: current behaviour — R1 + R2 + R3+ until policy-max or convergence, synthesise.

`--policy` CLI flag accepts `auto | best_r1_only | single_critique | full_debate`. `auto` is default.

- [ ] **Step 1: Failing test — low-diversity roster produces warning + best-R1 answer**

```python
# tests/e2e/test_headless_low_diversity_warning.py
from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.debate_policy import DebatePolicy
from council.domain.models import CouncilPack


async def test_low_diversity_mode_skips_debate_and_returns_best_r1(capsys):
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["R1 Claude only."]),
        "gemini": FakeElder(elder_id="gemini", replies=["R1 Gemini only."]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["R1 ChatGPT only."]),
    }
    judge = FakeElder(elder_id="claude", replies=["best: 1\nreason: first one.\n"])
    override = DebatePolicy(
        mode="best_r1_only", max_rounds=1,
        synthesise=False, always_compute_best_r1=True,
        warning="Low-diversity roster — forced mode for test.",
    )
    await run_headless(
        prompt="Q?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
        synthesizer="claude",
        best_r1_judge=judge,
        policy=override,
    )
    out = capsys.readouterr().out
    assert "Low-diversity roster" in out
    assert "R1 Claude only." in out  # best-R1 pick surfaced
    assert "Final synth." not in out  # synthesis did not run
    assert "Round 2" not in out
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/e2e/test_headless_low_diversity_warning.py -v`
Expected: FAIL — `policy` kwarg unsupported.

- [ ] **Step 3: Extend `run_headless` signature**

Add `policy: DebatePolicy | None = None` and, above the existing round loop, resolve it:

```python
from council.domain.debate_policy import DebatePolicy, policy_for
from council.domain.diversity import score_roster

effective_policy = policy
if effective_policy is None:
    # No roster_spec on run_headless yet — either plumb it through
    # from main() or pick a conservative default here. For now, require
    # callers to pass policy or roster_spec; if neither, fall back to
    # full_debate to preserve existing test behaviour.
    effective_policy = DebatePolicy(
        mode="full_debate", max_rounds=max_rounds,
        synthesise=True, always_compute_best_r1=True, warning=None,
    )

if effective_policy.warning:
    print(f"[warning] {effective_policy.warning}")
```

Then restructure the round loop:

```python
# Always R1.
await svc.run_round(debate)

if effective_policy.mode != "best_r1_only":
    await svc.run_round(debate)  # R2
    if effective_policy.mode == "full_debate":
        while len(debate.rounds) < effective_policy.max_rounds and not svc.rules.is_converged(
            debate.rounds[-1]
        ):
            await svc.run_round(debate)

# best-R1 (unchanged placement — after rounds, before synth)
...

# Synthesis conditional on policy.
if effective_policy.synthesise:
    synth = await svc.synthesize(debate, by=synthesizer)
    print(f"[Synthesis by {_LABELS[synthesizer]}] {synth.text}")
else:
    # Emit the best-R1 answer directly as the "final answer".
    if debate.best_r1_elder is not None:
        best_text = next(
            (t.answer.text for t in debate.rounds[0].turns if t.elder == debate.best_r1_elder),
            None,
        )
        if best_text:
            print(f"[Answer (best-R1, {_LABELS[debate.best_r1_elder]})] {best_text}")
```

- [ ] **Step 4: Plumb policy from `main()`**

In `main()`:

```python
from council.domain.diversity import score_roster
from council.domain.debate_policy import policy_for, DebatePolicy

# ... after build_elders returns roster_spec
user_override: DebatePolicy | None = None
if args.policy != "auto":
    user_override = DebatePolicy(
        mode=args.policy, max_rounds=args.max_rounds,
        synthesise=(args.policy != "best_r1_only"),
        always_compute_best_r1=True, warning=None,
    )
diversity = score_roster(roster_spec) if roster_spec.models else None
chosen_policy = user_override or (
    policy_for(diversity) if diversity is not None
    else DebatePolicy(mode="full_debate", max_rounds=args.max_rounds,
                     synthesise=True, always_compute_best_r1=True, warning=None)
)
```

Add the `--policy` argparse option:

```python
parser.add_argument(
    "--policy",
    choices=["auto", "best_r1_only", "single_critique", "full_debate"],
    default="auto",
    help="Pipeline mode. 'auto' picks from roster diversity.",
)
```

- [ ] **Step 5: Run full suite**

Run: `pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/app/headless/main.py tests/e2e/test_headless_low_diversity_warning.py
git commit -m "feat(policy): headless consumes adaptive debate policy"
```

---

## Stage 4 — Disagreement-preserving synthesis output

**Deliverable:** Synthesis emits an Answer / Why / Disagreements structure. The parser tolerates missing sections. The headless output prints the structure; the report puts disagreements in a primary section, not only the audit.

### Task 4.1 — `SynthesisOutput` dataclass + parser

**Files:**
- Create: `council/domain/synthesis_output.py`
- Create: `tests/unit/test_synthesis_output.py`

Accepted wire format (the prompt will instruct the model to use these exact labels):

```
ANSWER:
<the answer itself — free prose or structure the user asked for>

WHY:
<one short paragraph, 1-3 sentences>

DISAGREEMENTS:
- <one bullet per decision-relevant disagreement; may be empty>
- <or literal "(none)" when harmonious>
```

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_synthesis_output.py
from council.domain.synthesis_output import SynthesisOutput, parse_synthesis


class TestParseSynthesis:
    def test_happy_path_all_three_sections(self):
        raw = (
            "ANSWER:\nHire one senior.\n\n"
            "WHY:\nOne senior clears blockers juniors can't.\n\n"
            "DISAGREEMENTS:\n- Claude preferred three juniors for parallelism.\n"
            "- ChatGPT flagged onboarding cost.\n"
        )
        out = parse_synthesis(raw)
        assert out.answer == "Hire one senior."
        assert "One senior clears" in out.why
        assert len(out.disagreements) == 2
        assert "three juniors" in out.disagreements[0]

    def test_none_marker_yields_empty_disagreements(self):
        raw = (
            "ANSWER:\nSQLite.\n\nWHY:\n50 users is well within SQLite's range.\n\n"
            "DISAGREEMENTS:\n(none)\n"
        )
        out = parse_synthesis(raw)
        assert out.answer == "SQLite."
        assert out.disagreements == ()

    def test_missing_disagreements_section_is_empty(self):
        raw = "ANSWER:\nx\n\nWHY:\ny\n"
        out = parse_synthesis(raw)
        assert out.disagreements == ()

    def test_missing_answer_falls_back_to_full_raw(self):
        raw = "Hire one senior."  # model ignored the format
        out = parse_synthesis(raw)
        assert out.answer == "Hire one senior."
        assert out.why == ""
        assert out.disagreements == ()
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/unit/test_synthesis_output.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# council/domain/synthesis_output.py
"""Structured synthesis output — Answer / Why / Disagreements.

The synthesiser is prompted to emit three labelled sections. Parsing
is tolerant: missing sections default to empty; if no recognised label
is present at all, the full raw text is treated as the answer (so a
rule-ignoring model still produces a usable deliverable).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ANSWER_RE = re.compile(
    r"^\s*ANSWER\s*:\s*\n(.*?)(?=\n\s*(?:WHY|DISAGREEMENTS)\s*:\s*\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_WHY_RE = re.compile(
    r"^\s*WHY\s*:\s*\n(.*?)(?=\n\s*(?:ANSWER|DISAGREEMENTS)\s*:\s*\n|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)
_DISAGREEMENTS_RE = re.compile(
    r"^\s*DISAGREEMENTS\s*:\s*\n(.*?)(?=\n\s*(?:ANSWER|WHY)\s*:\s*\n|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)


@dataclass(frozen=True)
class SynthesisOutput:
    answer: str
    why: str
    disagreements: tuple[str, ...]
    raw: str


def parse_synthesis(raw: str) -> SynthesisOutput:
    body = raw.strip()
    answer_m = _ANSWER_RE.search(body)
    why_m = _WHY_RE.search(body)
    disag_m = _DISAGREEMENTS_RE.search(body)

    if answer_m is None and why_m is None and disag_m is None:
        return SynthesisOutput(answer=body, why="", disagreements=(), raw=raw)

    answer = answer_m.group(1).strip() if answer_m else ""
    why = why_m.group(1).strip() if why_m else ""
    disagreements: tuple[str, ...] = ()
    if disag_m:
        block = disag_m.group(1).strip()
        if block.lower() != "(none)":
            items = [
                re.sub(r"^[-*]\s*", "", line).strip()
                for line in block.splitlines()
                if line.strip() and line.strip().lower() != "(none)"
            ]
            disagreements = tuple(items)
    return SynthesisOutput(answer=answer, why=why, disagreements=disagreements, raw=raw)
```

- [ ] **Step 4: Run**

Run: `pytest tests/unit/test_synthesis_output.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/domain/synthesis_output.py tests/unit/test_synthesis_output.py
git commit -m "feat(synthesis): Answer/Why/Disagreements structured output parser"
```

---

### Task 4.2 — Rewrite synthesis prompt to emit the structure

**Files:**
- Modify: `council/domain/prompting.py`
- Modify: `tests/unit/test_prompting.py`

Replace the body of `PromptBuilder.build_synthesis` so the final block instructs the model to emit exactly the three labelled sections. Keep the "synthesize don't select" discipline and form/length calibration — just change the *output format*.

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_prompting.py  (append)
def test_synthesis_prompt_requests_answer_why_disagreements_structure():
    from council.domain.models import CouncilPack, Debate
    from council.domain.prompting import PromptBuilder

    debate = Debate(
        id="x", prompt="Q?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[], status="in_progress", synthesis=None,
    )
    prompt = PromptBuilder().build_synthesis(debate, by="claude")
    assert "ANSWER:" in prompt
    assert "WHY:" in prompt
    assert "DISAGREEMENTS:" in prompt
    assert "decision-relevant" in prompt.lower()
```

- [ ] **Step 2: Run — verify fails**

Run: `pytest tests/unit/test_prompting.py -v -k synthesis_prompt_requests_answer`
Expected: FAIL.

- [ ] **Step 3: Rewrite the synthesis closer**

Replace the closing prose paragraph inside `PromptBuilder.build_synthesis` (the block that currently begins "You have seen every advisor across every round…") with:

```python
parts.append(
    "You have seen every advisor across every round. Write the final "
    "answer the user receives.\n\n"
    "**Form and length.** Match the shape and brevity the user's "
    'request implies. "One sentence" means one short sentence. '
    '"Headline," "slogan," "tagline," "tweet," "short answer" mean '
    "genuinely punchy. Calibrate to the user's ask, not to the transcript "
    "length. Add no structure beyond what the user requested inside the "
    "ANSWER section.\n\n"
    "**Synthesize, do not select.** Take the strongest formulation of "
    "each component from whichever advisor expressed it best, and write "
    "it in your own voice. Where advisors disagreed, decide on the "
    "strongest argument and output only your decision.\n\n"
    "**Output format.** Emit exactly these three labelled sections in "
    "this order, with the labels flush-left in uppercase as shown. Do "
    "not add any text before ANSWER: or after the last DISAGREEMENTS "
    "bullet. No preamble, no sign-off.\n\n"
    "ANSWER:\n"
    "<the answer itself — the user-facing deliverable, no other labels>\n\n"
    "WHY:\n"
    "<1-3 short sentences on the load-bearing reason>\n\n"
    "DISAGREEMENTS:\n"
    "- <one bullet per DECISION-RELEVANT disagreement between advisors; "
    "a difference counts only if it would change action, interpretation, "
    "scope, caveats, confidence, or edge-case handling>\n"
    "- <skip stylistic differences; skip minor framing gaps>\n"
    "\n"
    "If advisors agreed on everything decision-relevant, write exactly "
    "`(none)` as the only line under DISAGREEMENTS."
)
```

- [ ] **Step 4: Run the prompting test + any existing synthesis tests**

Run: `pytest tests/unit/test_prompting.py tests/unit/test_debate_service.py tests/unit/test_synthesis_validation.py -v`
Expected: The new test passes. Some existing tests may need fixture updates if they grep for specific phrases from the old prompt — adjust them to grep for the relevant new substring (e.g. "Synthesize, do not select").

- [ ] **Step 5: Commit**

```bash
git add council/domain/prompting.py tests/unit/test_prompting.py
git commit -m "feat(synthesis): prompt emits Answer/Why/Disagreements structure"
```

---

### Task 4.3 — Surface disagreements in headless + report

**Files:**
- Modify: `council/app/headless/main.py`
- Modify: `council/domain/reporting.py`
- Modify: `tests/e2e/test_headless_flow.py` (the test asserting "Final synth." can be extended to assert the structured labels once we stop routing through the legacy print path)

- [ ] **Step 1: Update headless print of synthesis**

Replace:

```python
print(f"[Synthesis by {_LABELS[synthesizer]}] {synth.text}")
```

with:

```python
from council.domain.synthesis_output import parse_synthesis

structured = parse_synthesis(synth.text or "")
print(f"\n[Synthesis by {_LABELS[synthesizer]}]\n")
print(structured.answer)
if structured.why:
    print(f"\nWhy: {structured.why}")
if structured.disagreements:
    print("\nDisagreements:")
    for d in structured.disagreements:
        print(f"- {d}")
elif structured.why:
    print("\nDisagreements: none material.")
```

- [ ] **Step 2: Add a "Disagreements" primary section to the report**

In `council/domain/reporting.py`, extend `assemble_report_markdown` so that BEFORE the "Debate metadata" section, if synthesis parses into structured form with non-empty `disagreements`, a section is emitted:

```python
structured = parse_synthesis(synthesis.text or "")
if structured.disagreements:
    parts.append("## Unresolved disagreements")
    parts.append("")
    for d in structured.disagreements:
        parts.append(f"- {d}")
    parts.append("")
```

Put this *before* `build_metadata_section(debate)` so the reader sees it early.

- [ ] **Step 3: Run full suite**

Run: `pytest -v`
Expected: PASS (may need to adjust the existing headless-flow tests that grep for `[Synthesis by ...]` prefix — they still work because the literal prefix is preserved).

- [ ] **Step 4: Commit**

```bash
git add council/app/headless/main.py council/domain/reporting.py tests/e2e/test_headless_flow.py
git commit -m "feat(output): surface disagreements in headless output and report"
```

---

## Stage 5 — Convergence reframe, observability, experiment scaffolds

**Deliverable:** Convergence no longer terminates rounds early (policy budget governs rounds). Each debate run emits a `run_summary.json`. A new `diversity_split` experiment module scaffolds the 2×2 model-vs-role matrix. A `scripts/judge_replication.py` scaffold re-scores an existing homogenisation run with GPT-5 and Sonnet as judges.

### Task 5.1 — Drop early-termination on convergence

**Files:**
- Modify: `council/app/headless/main.py`
- Modify: `council/experiments/homogenisation/runner.py`

In `full_debate` mode, replace `and not svc.rules.is_converged(debate.rounds[-1])` with just `len(debate.rounds) < effective_policy.max_rounds`. Convergence becomes informational, not a stop signal.

Existing tests `test_headless_early_terminates_on_convergence` will need updating — it now runs to max-rounds regardless. Rename to `test_headless_runs_full_policy_budget_even_when_converged`.

- [ ] **Step 1: Update test expectation first**

Rewrite the `test_headless_early_terminates_on_convergence` assertion from "exactly 3 rounds printed" to "up to max_rounds printed, regardless of CONVERGED tags".

- [ ] **Step 2: Run — verify it now fails under the current code (since early-term kicks in)**

Run: `pytest tests/e2e/test_headless_flow.py::test_headless_runs_full_policy_budget_even_when_converged -v`
Expected: FAIL — still early-terminates.

- [ ] **Step 3: Remove the convergence short-circuit**

In `council/app/headless/main.py`:

```python
if effective_policy.mode == "full_debate":
    while len(debate.rounds) < effective_policy.max_rounds:
        await svc.run_round(debate)
```

Same change in `council/experiments/homogenisation/runner.py::_run_one_debate`.

- [ ] **Step 4: Run**

Run: `pytest tests/e2e/test_headless_flow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/app/headless/main.py council/experiments/homogenisation/runner.py tests/e2e/test_headless_flow.py
git commit -m "refactor: convergence no longer terminates rounds early"
```

---

### Task 5.2 — Per-run `run_summary.json`

**Files:**
- Modify: `council/app/headless/main.py`
- Create: `tests/e2e/test_headless_run_summary.py`

Write the JSON to `<reports-root>/<debate-id>-summary.json`. Fields:

```json
{
  "debate_id": "...",
  "prompt": "...",
  "roster": {"name": "openrouter", "models": {"claude": "...", ...}},
  "diversity": {"classification": "high", "provider_count": 3, "flags": [...]},
  "policy": {"mode": "full_debate", "max_rounds": 6},
  "rounds_executed": 4,
  "best_r1_elder": "gemini",
  "synthesis_generated": true,
  "synthesis_structured": {"answer": "...", "why": "...", "disagreements": [...]}
}
```

- [ ] **Step 1: Failing test**
- [ ] **Step 2: Implement** — emit JSON at end of `run_headless`.
- [ ] **Step 3: Run + commit**

```bash
git add council/app/headless/main.py tests/e2e/test_headless_run_summary.py
git commit -m "feat(observability): emit per-debate run_summary.json"
```

---

### Task 5.3 — `diversity_split` experiment scaffold (model × role 2×2)

**Files:**
- Create: `council/experiments/diversity_split/__init__.py`
- Create: `council/experiments/diversity_split/rosters.py` (4 specs: same/diff model × same/diff role)
- Create: `council/experiments/diversity_split/runner.py` (thin — reuse homogenisation runner + judges)
- Create: `scripts/diversity_split.py` (CLI entry)
- Create: `tests/unit/test_diversity_split_rosters.py`

No implementation of the run itself yet — just the rosters + CLI stub. The four conditions:
- A: same model (gpt-5-mini), same role/pack (no persona)
- B: same model, different persona (pre-baked packs)
- C: different model (sonnet / gemini-pro / gpt-5), same pack
- D: different model, different persona

- [ ] **Step 1: Write the roster specs + test listing their ids**
- [ ] **Step 2: Runner stubs to `raise NotImplementedError`** (real implementation deferred; this is scaffold only)
- [ ] **Step 3: Commit**

```bash
git add council/experiments/diversity_split/ scripts/diversity_split.py tests/unit/test_diversity_split_rosters.py
git commit -m "feat(experiments): scaffold model-vs-role 2x2 diversity experiment"
```

---

### Task 5.4 — Judge-swap replication scaffold

**Files:**
- Create: `scripts/judge_replication.py`
- Create: `tests/unit/test_judge_replication.py`

CLI:

```
python scripts/judge_replication.py --run-id 2026-04-19-9288 \
    --judge-models openai/gpt-5,anthropic/claude-sonnet-4.5
```

Re-scores the existing run's debates with each alternative judge, writing `scores-<judge-slug>.json` next to the existing `scores.json`. Reuses `council.experiments.homogenisation.scorer.score_probe` with a different `judge_port`.

- [ ] **Step 1: CLI stub + dispatch** (mostly glue around `score_probe`)
- [ ] **Step 2: Commit**

```bash
git add scripts/judge_replication.py tests/unit/test_judge_replication.py
git commit -m "feat(experiments): judge-swap replication scaffold"
```

---

## Self-review

**Spec coverage** (against the 7-priority brief):
- (1) Roster diversity visible + actionable → Stage 1 (`score_roster`, bootstrap exposes roster), Stage 3 warning.
- (2) Adaptive debate depth → Stage 3 (`policy_for`, three modes).
- (3) Preserve disagreement → Stage 4 (Answer/Why/Disagreements synthesis + report section).
- (4) Best-R1 mandatory baseline → Stage 2 (LLM-judged; always computed when key present).
- (5) Separate model diversity vs role diversity → Stage 5.3 scaffold.
- (6) Improve observability → Stage 5.2 `run_summary.json`.
- (7) Task-specific rosters — deferred per user decision.

**Pushbacks folded in (from prior session):**
- Warn, don't block, on low diversity → Stage 3 Task 3.2.
- Tier-1 heuristic only, calibration deferred → documented in Stage 1 rationale; Stage 5.4 judge-swap replication scaffold unblocks calibration.
- Priority #3 reframed as output-shape change → Stage 4 is output-shape, not synthesis-logic rewrite.
- Calibration surface → judge-swap replication (5.4) + future task-to-empirical-diversity mapping (out of scope for this plan).

**Type consistency:** `DiversityScore.classification` is the `DiversityClass` Literal (low/medium/high). `DebatePolicy.mode` is `PolicyMode` (best_r1_only/single_critique/full_debate). `BestR1Selection.elder` is `ElderId`. `SynthesisOutput.disagreements` is `tuple[str, ...]`. All consistent across tasks.

**Placeholder scan:** one TODO-shaped spot remains in Task 3.2 Step 3 where a fallback `DebatePolicy` is constructed when policy not passed; that's explicit fallback, not a placeholder. Clear.
