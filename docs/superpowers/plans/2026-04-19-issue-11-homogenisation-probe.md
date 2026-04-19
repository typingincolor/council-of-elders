# Homogenisation probe implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the homogenisation probe script specified in `docs/superpowers/specs/2026-04-19-issue-11-homogenisation-test-design.md` — a research experiment that measures R1 claim-Jaccard and synthesis-vs-best-R1 preference across three rosters (homogeneous, mixed baseline, open-weights substituted) over an 8-prompt corpus, emitting a markdown report.

**Architecture:** Thin CLI (`scripts/homogenisation_probe.py`) dispatches to a `council.experiments.homogenisation` package split into six focused modules (corpus, rosters, judges, runner, scorer, reporter). Debate execution reuses the existing `DebateService`; judges are new and share a single `_call_judge` helper around `OpenRouterAdapter`. All three phases are idempotent and resumable via artifacts on disk.

**Tech Stack:** Python 3.12, existing project deps only (`httpx`, `pytest`, `pytest-asyncio`). No new dependencies.

---

## Shared types (referenced across tasks)

These dataclasses are defined inside their respective modules. Listed here for reference so later tasks don't drift from earlier ones.

```python
# corpus.py
@dataclass(frozen=True)
class CorpusPrompt:
    id: str
    shape: str  # "headline" | "summary" | "strategy_tradeoff" | ...
    prompt: str

# rosters.py
@dataclass(frozen=True)
class RosterSpec:
    name: str  # "homogeneous" | "mixed_baseline" | "substituted"
    models: dict[ElderId, str]  # {"claude": "...", "gemini": "...", "chatgpt": "..."}

# judges.py
@dataclass(frozen=True)
class JaccardObservation:
    shared: int
    a_only: int
    b_only: int
    note: str
    raw: str

    @property
    def jaccard(self) -> float:
        total = self.shared + self.a_only + self.b_only
        return self.shared / total if total else 0.0

@dataclass(frozen=True)
class BestR1Observation:
    best_index: int  # 1 | 2 | 3
    reason: str
    raw: str

@dataclass(frozen=True)
class PreferenceObservation:
    winner: str  # "synthesis" | "best_r1" | "tie" (resolved from X/Y)
    reason: str
    raw: str
    x_was: str  # "synthesis" or "best_r1" — what the X slot contained

# scorer.py
@dataclass(frozen=True)
class DebateScoreRow:
    debate_id: str
    roster: str
    prompt_id: str
    r1_jaccard: float  # mean of 3 pairwise
    preference_winner: str  # "synthesis" | "best_r1" | "tie"

@dataclass(frozen=True)
class RosterSummary:
    roster: str
    n_debates: int
    mean_r1_jaccard: float
    median_r1_jaccard: float
    preference_rate: float  # synthesis wins / n, ties = 0.5
    preference_ci_lo: float  # 90% binomial CI lower bound
    preference_ci_hi: float
```

---

## File layout (new files)

```
council/experiments/
    __init__.py                          (empty)
    homogenisation/
        __init__.py                      (empty — modules imported by path)
        corpus.py                        (CorpusPrompt, load_corpus)
        rosters.py                       (RosterSpec, ROSTERS, build_roster_elders)
        judges.py                        (three judge rubrics + parsers + callers)
        runner.py                        (phase 1: run debates, write manifest)
        scorer.py                        (phase 2: score debates, aggregate, write scores)
        reporter.py                      (phase 3: render markdown report)

scripts/
    homogenisation_probe.py              (thin CLI dispatch)
    homogenisation_corpus.json           (8 prompts)

tests/unit/
    test_homogenisation_corpus.py
    test_homogenisation_rosters.py
    test_homogenisation_judges.py
    test_homogenisation_runner.py
    test_homogenisation_scorer.py
    test_homogenisation_reporter.py

tests/e2e/
    test_homogenisation_probe.py         (full pipeline with fakes)
```

---

### Task 1: Corpus + loader

**Files:**
- Create: `scripts/homogenisation_corpus.json`
- Create: `council/experiments/__init__.py` (empty)
- Create: `council/experiments/homogenisation/__init__.py` (empty)
- Create: `council/experiments/homogenisation/corpus.py`
- Test: `tests/unit/test_homogenisation_corpus.py`

- [ ] **Step 1: Create empty package inits**

```bash
mkdir -p council/experiments/homogenisation
touch council/experiments/__init__.py
touch council/experiments/homogenisation/__init__.py
```

- [ ] **Step 2: Write the corpus JSON**

Create `scripts/homogenisation_corpus.json`:

```json
{
  "prompts": [
    {
      "id": "headline_001",
      "shape": "headline",
      "prompt": "Write a single-sentence headline (max 12 words) for a product launch where a UK payments startup announces a fee cut for small businesses."
    },
    {
      "id": "summary_001",
      "shape": "summary",
      "prompt": "In two sentences, explain to a non-technical reader what \"latency\" means in the context of a web API."
    },
    {
      "id": "strategy_001",
      "shape": "strategy_tradeoff",
      "prompt": "A founder has $150k to either hire one senior engineer or three junior engineers for a year. Give a recommendation in one paragraph."
    },
    {
      "id": "strategy_002",
      "shape": "strategy_tradeoff",
      "prompt": "A regional bookshop must pick one focus for the year: stronger e-commerce, or a programme of in-store author events. Recommend one, with reasoning."
    },
    {
      "id": "technical_001",
      "shape": "technical_decision",
      "prompt": "A Python service must process 1M small JSON files on one VM. Recommend asyncio or a process pool, with one paragraph of reasoning."
    },
    {
      "id": "technical_002",
      "shape": "technical_decision",
      "prompt": "An internal tool will serve ~50 users with light CRUD traffic. PostgreSQL or SQLite? One paragraph."
    },
    {
      "id": "factual_001",
      "shape": "factual_multipart",
      "prompt": "Name three distinct primary causes of the 2008 financial crisis. One sentence on each."
    },
    {
      "id": "value_001",
      "shape": "contested_value",
      "prompt": "Is it ethical for a company to use AI to monitor individual employee productivity? Take a clear position in one paragraph."
    }
  ]
}
```

- [ ] **Step 3: Write the failing test**

Create `tests/unit/test_homogenisation_corpus.py`:

```python
from pathlib import Path

from council.experiments.homogenisation.corpus import CorpusPrompt, load_corpus


def test_load_corpus_returns_all_eight_prompts(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(
        '{"prompts": ['
        '{"id": "p1", "shape": "headline", "prompt": "Q1?"},'
        '{"id": "p2", "shape": "summary", "prompt": "Q2?"}'
        ']}'
    )
    prompts = load_corpus(path)
    assert len(prompts) == 2
    assert prompts[0] == CorpusPrompt(id="p1", shape="headline", prompt="Q1?")
    assert prompts[1].shape == "summary"


def test_load_corpus_rejects_missing_fields(tmp_path: Path) -> None:
    import pytest

    path = tmp_path / "bad.json"
    path.write_text('{"prompts": [{"id": "p1", "prompt": "Q1?"}]}')  # missing shape
    with pytest.raises(KeyError):
        load_corpus(path)


def test_real_corpus_has_eight_prompts_with_unique_ids() -> None:
    path = Path(__file__).parents[2] / "scripts" / "homogenisation_corpus.json"
    prompts = load_corpus(path)
    assert len(prompts) == 8
    ids = [p.id for p in prompts]
    assert len(set(ids)) == 8
```

- [ ] **Step 4: Run test, verify it fails**

Run: `pytest tests/unit/test_homogenisation_corpus.py -v`
Expected: ImportError / ModuleNotFoundError for `council.experiments.homogenisation.corpus`.

- [ ] **Step 5: Implement the loader**

Create `council/experiments/homogenisation/corpus.py`:

```python
"""Corpus loader for the homogenisation probe.

The corpus is a flat JSON list of 8 prompts spanning the shapes issue 11
lists as priorities. Stored as data (not Python) so a user can edit
prompts without touching code between runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusPrompt:
    id: str
    shape: str
    prompt: str


def load_corpus(path: Path) -> list[CorpusPrompt]:
    """Load the homogenisation probe corpus from a JSON file.

    Raises KeyError if any prompt is missing required fields, so a
    malformed file fails fast at startup rather than mid-run.
    """
    data = json.loads(path.read_text())
    return [
        CorpusPrompt(id=p["id"], shape=p["shape"], prompt=p["prompt"])
        for p in data["prompts"]
    ]
```

- [ ] **Step 6: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_corpus.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add council/experiments scripts/homogenisation_corpus.json tests/unit/test_homogenisation_corpus.py
git commit -m "feat(homogenisation): corpus loader + 8-prompt fixture"
```

---

### Task 2: Roster specs + adapter factory

**Files:**
- Create: `council/experiments/homogenisation/rosters.py`
- Test: `tests/unit/test_homogenisation_rosters.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_homogenisation_rosters.py`:

```python
from council.experiments.homogenisation.rosters import (
    ROSTERS,
    RosterSpec,
    build_roster_elders,
)


def test_rosters_are_named_correctly() -> None:
    names = {r.name for r in ROSTERS}
    assert names == {"homogeneous", "mixed_baseline", "substituted"}


def test_homogeneous_roster_uses_same_model_in_all_slots() -> None:
    hom = next(r for r in ROSTERS if r.name == "homogeneous")
    assert hom.models["claude"] == hom.models["gemini"] == hom.models["chatgpt"]


def test_substituted_roster_places_llama_in_gemini_slot() -> None:
    sub = next(r for r in ROSTERS if r.name == "substituted")
    assert "llama" in sub.models["gemini"].lower()
    assert "claude" in sub.models["claude"].lower()
    assert "openai" in sub.models["chatgpt"].lower()


def test_build_roster_elders_returns_openrouter_adapters() -> None:
    from council.adapters.elders.openrouter import OpenRouterAdapter

    spec = RosterSpec(
        name="test",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        },
    )
    elders = build_roster_elders(spec, api_key="sk-test")
    assert set(elders.keys()) == {"claude", "gemini", "chatgpt"}
    for slot in ("claude", "gemini", "chatgpt"):
        assert isinstance(elders[slot], OpenRouterAdapter)
        assert elders[slot].model == spec.models[slot]
        assert elders[slot].api_key == "sk-test"
        assert elders[slot].elder_id == slot
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/unit/test_homogenisation_rosters.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement rosters**

Create `council/experiments/homogenisation/rosters.py`:

```python
"""Roster definitions and elder-adapter construction for the
homogenisation probe.

The three rosters isolate two mechanisms the council tool could
deliver value through: model diversity (mixed vs homogeneous) and
debate protocol (homogeneous vs single-model baseline). The
substituted roster is the original issue 11 question — does a
distant-lineage model widen diversity further?
"""

from __future__ import annotations

from dataclasses import dataclass

from council.adapters.elders.openrouter import OpenRouterAdapter
from council.domain.models import ElderId
from council.domain.ports import ElderPort


@dataclass(frozen=True)
class RosterSpec:
    name: str
    models: dict[ElderId, str]


ROSTERS: tuple[RosterSpec, ...] = (
    RosterSpec(
        name="homogeneous",
        models={
            "claude": "openai/gpt-5-mini",
            "gemini": "openai/gpt-5-mini",
            "chatgpt": "openai/gpt-5-mini",
        },
    ),
    RosterSpec(
        name="mixed_baseline",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        },
    ),
    RosterSpec(
        name="substituted",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "meta-llama/llama-3.1-70b-instruct",
            "chatgpt": "openai/gpt-5",
        },
    ),
)


def build_roster_elders(
    spec: RosterSpec, *, api_key: str
) -> dict[ElderId, ElderPort]:
    """Build a fresh {slot → OpenRouterAdapter} mapping for a roster.

    Adapters own their HTTP client implicitly via OpenRouterAdapter's
    per-call client creation, so each roster's adapters can be discarded
    at the end of its run without explicit cleanup.
    """
    return {
        slot: OpenRouterAdapter(elder_id=slot, model=model, api_key=api_key)
        for slot, model in spec.models.items()
    }
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_rosters.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/rosters.py tests/unit/test_homogenisation_rosters.py
git commit -m "feat(homogenisation): roster specs + adapter factory"
```

---

### Task 3: Judge rubrics + parsers (claim-overlap)

**Files:**
- Create: `council/experiments/homogenisation/judges.py`
- Test: `tests/unit/test_homogenisation_judges.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_homogenisation_judges.py`:

```python
from council.experiments.homogenisation.judges import (
    JaccardObservation,
    _parse_claim_overlap,
)


class TestParseClaimOverlap:
    def test_well_formed_response_parses(self) -> None:
        raw = (
            "shared_count: 3\n"
            "a_only_count: 1\n"
            "b_only_count: 2\n"
            "note: Both agreed on core recommendation.\n"
        )
        obs = _parse_claim_overlap(raw)
        assert obs == JaccardObservation(
            shared=3, a_only=1, b_only=2,
            note="Both agreed on core recommendation.", raw=raw,
        )

    def test_jaccard_property(self) -> None:
        obs = JaccardObservation(shared=3, a_only=1, b_only=2, note="", raw="")
        assert obs.jaccard == 0.5  # 3/6

    def test_jaccard_is_zero_when_all_counts_are_zero(self) -> None:
        obs = JaccardObservation(shared=0, a_only=0, b_only=0, note="", raw="")
        assert obs.jaccard == 0.0

    def test_case_insensitive_keys(self) -> None:
        raw = "SHARED_COUNT: 5\nA_ONLY_COUNT: 0\nB_ONLY_COUNT: 0\nNote: n/a\n"
        obs = _parse_claim_overlap(raw)
        assert obs.shared == 5 and obs.a_only == 0 and obs.b_only == 0

    def test_missing_counts_default_to_zero(self) -> None:
        raw = "note: judge did not emit counts\n"
        obs = _parse_claim_overlap(raw)
        assert obs.shared == 0 and obs.a_only == 0 and obs.b_only == 0

    def test_markdown_fence_stripped(self) -> None:
        raw = "```\nshared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n```\n"
        obs = _parse_claim_overlap(raw)
        assert obs.shared == 2
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/unit/test_homogenisation_judges.py::TestParseClaimOverlap -v`
Expected: ImportError.

- [ ] **Step 3: Implement the claim-overlap rubric + parser**

Create `council/experiments/homogenisation/judges.py`:

```python
"""Judge rubrics and parsers for the homogenisation probe.

Three judges, all using the same cheap judge model via OpenRouter:

- Claim-overlap (pairwise): compares two R1 answers, emits shared /
  a-only / b-only claim counts. Called 3 times per prompt per roster.
- Best-R1 picker: sees the three R1 answers, picks the strongest.
  Called 1 time per debate.
- Preference: compares best-R1 and synthesis, picks the better answer.
  Called 1 time per debate with X/Y randomisation.

All three follow the same pattern as `_parse_drift_verdict` in
`council/domain/debate_analytics.py`: regex-based tolerant parsing,
neutral defaults on missing fields, raw response retained for
diagnostics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---- Claim-overlap judge --------------------------------------------


@dataclass(frozen=True)
class JaccardObservation:
    shared: int
    a_only: int
    b_only: int
    note: str
    raw: str

    @property
    def jaccard(self) -> float:
        total = self.shared + self.a_only + self.b_only
        return self.shared / total if total else 0.0


CLAIM_OVERLAP_PROMPT = """You are a neutral judge comparing two answers to the same question, measuring CLAIM OVERLAP.

User's question:
<<<
{question}
>>>

Answer A:
<<<
{answer_a}
>>>

Answer B:
<<<
{answer_b}
>>>

For each distinct factual or evaluative claim either answer makes, classify it as:
- SHARED: both make this claim (possibly in different words)
- A_ONLY: only A makes it
- B_ONLY: only B makes it

"Claim" = an atomic assertion about the world, a recommendation, or a judgement (not a stylistic choice or framing decision). Two answers saying "X is faster" and "X outperforms on speed" are the same claim.

Emit EXACTLY these four lines, nothing else:
shared_count: N
a_only_count: N
b_only_count: N
note: one short sentence explaining any judgement calls."""


_SHARED_RE = re.compile(r"^\s*shared_count\s*:\s*(\d+)", re.MULTILINE | re.IGNORECASE)
_A_ONLY_RE = re.compile(r"^\s*a_only_count\s*:\s*(\d+)", re.MULTILINE | re.IGNORECASE)
_B_ONLY_RE = re.compile(r"^\s*b_only_count\s*:\s*(\d+)", re.MULTILINE | re.IGNORECASE)
_NOTE_RE = re.compile(r"^\s*note\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def _strip_markdown_fence(raw: str) -> str:
    return re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip(), flags=re.MULTILINE)


def _parse_claim_overlap(raw: str) -> JaccardObservation:
    cleaned = _strip_markdown_fence(raw)
    shared_m = _SHARED_RE.search(cleaned)
    a_only_m = _A_ONLY_RE.search(cleaned)
    b_only_m = _B_ONLY_RE.search(cleaned)
    note_m = _NOTE_RE.search(cleaned)
    return JaccardObservation(
        shared=int(shared_m.group(1)) if shared_m else 0,
        a_only=int(a_only_m.group(1)) if a_only_m else 0,
        b_only=int(b_only_m.group(1)) if b_only_m else 0,
        note=note_m.group(1).strip() if note_m else "",
        raw=raw,
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_judges.py::TestParseClaimOverlap -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/judges.py tests/unit/test_homogenisation_judges.py
git commit -m "feat(homogenisation): claim-overlap judge rubric + parser"
```

---

### Task 4: Best-R1 picker judge

**Files:**
- Modify: `council/experiments/homogenisation/judges.py`
- Modify: `tests/unit/test_homogenisation_judges.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/test_homogenisation_judges.py`:

```python
from council.experiments.homogenisation.judges import (
    BestR1Observation,
    _parse_best_r1,
)


class TestParseBestR1:
    def test_well_formed_response_parses(self) -> None:
        raw = "best: 2\nreason: Answer 2 cites concrete tradeoffs.\n"
        obs = _parse_best_r1(raw)
        assert obs == BestR1Observation(
            best_index=2, reason="Answer 2 cites concrete tradeoffs.", raw=raw,
        )

    def test_default_on_unparsable(self) -> None:
        obs = _parse_best_r1("gibberish")
        assert obs.best_index == 1  # documented safe default
        assert obs.reason == ""

    def test_rejects_out_of_range(self) -> None:
        obs = _parse_best_r1("best: 7\nreason: invalid\n")
        assert obs.best_index == 1  # out-of-range falls back to default

    def test_case_insensitive_key(self) -> None:
        obs = _parse_best_r1("BEST: 3\nREASON: all clear\n")
        assert obs.best_index == 3
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/unit/test_homogenisation_judges.py::TestParseBestR1 -v`
Expected: ImportError for `BestR1Observation`.

- [ ] **Step 3: Add best-R1 rubric + parser**

Append to `council/experiments/homogenisation/judges.py`:

```python
# ---- Best-R1 picker judge -------------------------------------------


@dataclass(frozen=True)
class BestR1Observation:
    best_index: int  # 1, 2, or 3
    reason: str
    raw: str


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


def _parse_best_r1(raw: str) -> BestR1Observation:
    cleaned = _strip_markdown_fence(raw)
    best_m = _BEST_RE.search(cleaned)
    reason_m = _REASON_RE.search(cleaned)
    return BestR1Observation(
        best_index=int(best_m.group(1)) if best_m else 1,
        reason=reason_m.group(1).strip() if reason_m else "",
        raw=raw,
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_judges.py -v`
Expected: 10 passed (6 claim-overlap + 4 best-R1).

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/judges.py tests/unit/test_homogenisation_judges.py
git commit -m "feat(homogenisation): best-R1 picker judge"
```

---

### Task 5: Preference judge with X/Y randomisation

**Files:**
- Modify: `council/experiments/homogenisation/judges.py`
- Modify: `tests/unit/test_homogenisation_judges.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/test_homogenisation_judges.py`:

```python
import random

from council.experiments.homogenisation.judges import (
    PreferenceObservation,
    _parse_preference,
    _resolve_preference_winner,
    _shuffle_xy,
)


class TestShuffleXY:
    def test_reproducible_with_same_seed(self) -> None:
        rng_a = random.Random(42)
        rng_b = random.Random(42)
        x1, y1, x_was1 = _shuffle_xy("S", "R", rng_a)
        x2, y2, x_was2 = _shuffle_xy("S", "R", rng_b)
        assert (x1, y1, x_was1) == (x2, y2, x_was2)

    def test_shuffle_either_assigns_synthesis_to_x_or_y(self) -> None:
        # Over many trials we should see both assignments.
        seen: set[str] = set()
        for seed in range(20):
            _, _, x_was = _shuffle_xy("synth", "best", random.Random(seed))
            seen.add(x_was)
            if seen == {"synthesis", "best_r1"}:
                break
        assert seen == {"synthesis", "best_r1"}


class TestParsePreference:
    def test_winner_x_when_synthesis_is_x(self) -> None:
        raw = "winner: X\nreason: more direct.\n"
        obs = _parse_preference(raw, x_was="synthesis")
        assert obs.winner == "synthesis"
        assert obs.x_was == "synthesis"

    def test_winner_y_when_synthesis_is_x(self) -> None:
        raw = "winner: Y\nreason: better facts.\n"
        obs = _parse_preference(raw, x_was="synthesis")
        assert obs.winner == "best_r1"

    def test_winner_y_when_synthesis_is_y(self) -> None:
        raw = "winner: Y\nreason: clearer.\n"
        obs = _parse_preference(raw, x_was="best_r1")
        assert obs.winner == "synthesis"

    def test_tie(self) -> None:
        obs = _parse_preference("winner: TIE\nreason: equivalent.\n", x_was="synthesis")
        assert obs.winner == "tie"

    def test_unparsable_defaults_to_tie(self) -> None:
        obs = _parse_preference("blah blah", x_was="synthesis")
        assert obs.winner == "tie"


def test_resolve_preference_winner_handles_all_cases() -> None:
    assert _resolve_preference_winner("X", "synthesis") == "synthesis"
    assert _resolve_preference_winner("Y", "synthesis") == "best_r1"
    assert _resolve_preference_winner("X", "best_r1") == "best_r1"
    assert _resolve_preference_winner("Y", "best_r1") == "synthesis"
    assert _resolve_preference_winner("TIE", "synthesis") == "tie"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_homogenisation_judges.py::TestShuffleXY tests/unit/test_homogenisation_judges.py::TestParsePreference -v`
Expected: ImportError.

- [ ] **Step 3: Add preference judge**

Append to `council/experiments/homogenisation/judges.py`:

```python
# ---- Preference judge -----------------------------------------------


@dataclass(frozen=True)
class PreferenceObservation:
    winner: str  # "synthesis" | "best_r1" | "tie"
    reason: str
    raw: str
    x_was: str  # "synthesis" or "best_r1"


PREFERENCE_PROMPT = """You are judging which of two answers better addresses the question.

User's question:
<<<
{question}
>>>

Answer X:
<<<
{answer_x}
>>>

Answer Y:
<<<
{answer_y}
>>>

Judge on: factual correctness, completeness, shape-fit (does the form match what was asked for — e.g., headline vs essay), and avoidance of bloat. DO NOT favour an answer just because it is longer or more formal — penalise bloat.

Emit EXACTLY:
winner: X | Y | TIE
reason: one sentence."""


_WINNER_RE = re.compile(r"^\s*winner\s*:\s*(X|Y|TIE)\b", re.MULTILINE | re.IGNORECASE)


def _shuffle_xy(
    synthesis: str, best_r1: str, rng: "random.Random"
) -> tuple[str, str, str]:
    """Randomly decide whether synthesis goes to the X or Y slot.

    Returns (answer_x_text, answer_y_text, x_was) where `x_was` is
    "synthesis" or "best_r1". Use a seeded `random.Random` for
    reproducibility.
    """
    import random as _random

    if isinstance(rng, _random.Random) and rng.random() < 0.5:
        return synthesis, best_r1, "synthesis"
    return best_r1, synthesis, "best_r1"


def _resolve_preference_winner(x_or_y: str, x_was: str) -> str:
    if x_or_y.upper() == "TIE":
        return "tie"
    other = "best_r1" if x_was == "synthesis" else "synthesis"
    if x_or_y.upper() == "X":
        return x_was
    return other


def _parse_preference(raw: str, *, x_was: str) -> PreferenceObservation:
    cleaned = _strip_markdown_fence(raw)
    winner_m = _WINNER_RE.search(cleaned)
    reason_m = _REASON_RE.search(cleaned)
    if winner_m is None:
        return PreferenceObservation(winner="tie", reason="", raw=raw, x_was=x_was)
    winner = _resolve_preference_winner(winner_m.group(1), x_was)
    return PreferenceObservation(
        winner=winner,
        reason=reason_m.group(1).strip() if reason_m else "",
        raw=raw,
        x_was=x_was,
    )
```

Also add `import random` near the top of `judges.py` (under `import re`).

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_judges.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/judges.py tests/unit/test_homogenisation_judges.py
git commit -m "feat(homogenisation): preference judge with X/Y randomisation"
```

---

### Task 6: Judge call dispatch (async)

**Files:**
- Modify: `council/experiments/homogenisation/judges.py`
- Modify: `tests/unit/test_homogenisation_judges.py`

Adds the thin async callers that wrap each judge with a real `ElderPort` and format the prompt template. The `ElderPort` protocol already exists (`council/domain/ports.py`) — we accept any port that implements `ask(conversation, *, timeout_s)`.

- [ ] **Step 1: Add failing async tests**

Append to `tests/unit/test_homogenisation_judges.py`:

```python
import random

import pytest

from council.adapters.elders.fake import FakeElder
from council.experiments.homogenisation.judges import (
    judge_best_r1,
    judge_claim_overlap,
    judge_preference,
)


@pytest.mark.asyncio
async def test_judge_claim_overlap_formats_prompt_and_parses_reply() -> None:
    judge = FakeElder(
        elder_id="claude",  # elder_id is arbitrary for judges
        replies=["shared_count: 4\na_only_count: 1\nb_only_count: 1\nnote: ok\n"],
    )
    obs = await judge_claim_overlap(
        question="Q?", answer_a="alpha", answer_b="beta", judge_port=judge,
    )
    assert obs.shared == 4 and obs.jaccard == 4 / 6
    conv = judge.conversations[0]
    assert "Q?" in conv[0][1]  # prompt body contains the question
    assert "alpha" in conv[0][1] and "beta" in conv[0][1]


@pytest.mark.asyncio
async def test_judge_best_r1_returns_parsed_obs() -> None:
    judge = FakeElder(elder_id="claude", replies=["best: 2\nreason: fewer hedges.\n"])
    obs = await judge_best_r1(
        question="Q?", answers=("a1", "a2", "a3"), judge_port=judge,
    )
    assert obs.best_index == 2


@pytest.mark.asyncio
async def test_judge_preference_uses_shuffle_and_resolves_winner() -> None:
    judge = FakeElder(elder_id="claude", replies=["winner: X\nreason: tighter.\n"])
    rng = random.Random(0)  # rng.random() < 0.5 → synthesis goes to X
    obs = await judge_preference(
        question="Q?", best_r1="r1-text", synthesis="synth-text",
        judge_port=judge, rng=rng,
    )
    # With seed 0, synthesis is in X slot; winner X resolves to synthesis.
    assert obs.winner == "synthesis"
    assert obs.x_was == "synthesis"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_homogenisation_judges.py -v -k "judge_"`
Expected: ImportError for `judge_claim_overlap` et al.

- [ ] **Step 3: Add judge callers**

Append to `council/experiments/homogenisation/judges.py`:

```python
# ---- Judge call dispatch --------------------------------------------


from council.domain.models import Message
from council.domain.ports import ElderPort


async def judge_claim_overlap(
    *, question: str, answer_a: str, answer_b: str, judge_port: ElderPort
) -> JaccardObservation:
    prompt = CLAIM_OVERLAP_PROMPT.format(
        question=question.strip(),
        answer_a=answer_a.strip(),
        answer_b=answer_b.strip(),
    )
    raw = await judge_port.ask([Message("user", prompt)])
    return _parse_claim_overlap(raw)


async def judge_best_r1(
    *, question: str, answers: tuple[str, str, str], judge_port: ElderPort
) -> BestR1Observation:
    prompt = BEST_R1_PROMPT.format(
        question=question.strip(),
        answer_1=answers[0].strip(),
        answer_2=answers[1].strip(),
        answer_3=answers[2].strip(),
    )
    raw = await judge_port.ask([Message("user", prompt)])
    return _parse_best_r1(raw)


async def judge_preference(
    *,
    question: str,
    best_r1: str,
    synthesis: str,
    judge_port: ElderPort,
    rng: random.Random,
) -> PreferenceObservation:
    answer_x, answer_y, x_was = _shuffle_xy(synthesis, best_r1, rng)
    prompt = PREFERENCE_PROMPT.format(
        question=question.strip(),
        answer_x=answer_x.strip(),
        answer_y=answer_y.strip(),
    )
    raw = await judge_port.ask([Message("user", prompt)])
    return _parse_preference(raw, x_was=x_was)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_judges.py -v`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/judges.py tests/unit/test_homogenisation_judges.py
git commit -m "feat(homogenisation): async judge call dispatchers"
```

---

### Task 7: Runner (phase 1)

**Files:**
- Create: `council/experiments/homogenisation/runner.py`
- Test: `tests/unit/test_homogenisation_runner.py`

Runs one full debate per (roster, prompt), stores each via `JsonFileStore`, writes a manifest mapping `(roster_name, prompt_id) → debate_id`. Idempotent: if the manifest already has an entry, skip.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_homogenisation_runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from council.adapters.elders.fake import FakeElder
from council.domain.models import ElderId
from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.rosters import RosterSpec
from council.experiments.homogenisation.runner import run_probe


def _mk_elders() -> dict[ElderId, FakeElder]:
    """Scripted fake elders with enough replies for a 3-round debate + synth."""
    r1 = "R1 answer from {slot}"
    r2 = "CONVERGED: no\n\nR2 answer\n\nQUESTIONS:\n@chatgpt why?"
    r3 = "CONVERGED: yes\n\nR3 final"
    synth = "Synthesised answer."
    # Enough replies across rounds + synthesis. DebateService may make
    # additional calls for the narrative audit and report — pad.
    def make(slot: ElderId) -> FakeElder:
        return FakeElder(
            elder_id=slot,
            replies=[
                r1.format(slot=slot), r2, r3, synth,
                "Report body.", "Narrative audit body.",
            ],
        )
    return {slot: make(slot) for slot in ("claude", "gemini", "chatgpt")}


@pytest.mark.asyncio
async def test_run_probe_produces_manifest_with_every_pair(tmp_path: Path) -> None:
    # Build runner with an injected elder-factory so we don't need OpenRouter.
    prompts = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    specs = (
        RosterSpec(name="r1", models={"claude": "a/a", "gemini": "a/a", "chatgpt": "a/a"}),
        RosterSpec(name="r2", models={"claude": "b/b", "gemini": "b/b", "chatgpt": "b/b"}),
    )

    # Injected elder-factory gives us FakeElders regardless of roster.
    def elder_factory(_spec: RosterSpec) -> dict[ElderId, Any]:
        return _mk_elders()

    run_id = "2026-04-19-test"
    manifest_path = await run_probe(
        rosters=specs, prompts=prompts, run_id=run_id,
        runs_root=tmp_path, debate_store_root=tmp_path / "debates",
        elder_factory=elder_factory, max_rounds=3, synthesiser="claude",
    )
    manifest = json.loads(Path(manifest_path).read_text())
    assert len(manifest["entries"]) == 2  # 2 rosters × 1 prompt
    rosters_seen = {e["roster"] for e in manifest["entries"]}
    assert rosters_seen == {"r1", "r2"}
    assert all("debate_id" in e for e in manifest["entries"])


@pytest.mark.asyncio
async def test_run_probe_is_resumable(tmp_path: Path) -> None:
    """A second run with the same run_id should skip already-done pairs."""
    prompts = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    specs = (RosterSpec(name="r1", models={"claude": "a/a", "gemini": "a/a", "chatgpt": "a/a"}),)

    calls = {"n": 0}

    def elder_factory(_spec: RosterSpec) -> dict[ElderId, Any]:
        calls["n"] += 1
        return _mk_elders()

    run_id = "2026-04-19-test"
    await run_probe(
        rosters=specs, prompts=prompts, run_id=run_id,
        runs_root=tmp_path, debate_store_root=tmp_path / "debates",
        elder_factory=elder_factory, max_rounds=3, synthesiser="claude",
    )
    await run_probe(  # second call, should skip
        rosters=specs, prompts=prompts, run_id=run_id,
        runs_root=tmp_path, debate_store_root=tmp_path / "debates",
        elder_factory=elder_factory, max_rounds=3, synthesiser="claude",
    )
    assert calls["n"] == 1  # second call skipped entirely
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_homogenisation_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the runner**

Create `council/experiments/homogenisation/runner.py`:

```python
"""Phase 1 of the homogenisation probe: run one debate per (roster,
prompt) pair and record debate IDs in a manifest file.

Debates are persisted via the existing JsonFileStore so later phases
can read full debate objects. Already-completed (roster, prompt)
pairs are skipped, making the runner safe to restart after a failure
without double-spending on API calls.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.storage.json_file import JsonFileStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate, ElderId
from council.domain.ports import ElderPort
from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.rosters import RosterSpec

ElderFactory = Callable[[RosterSpec], dict[ElderId, ElderPort]]


def _manifest_path(runs_root: Path, run_id: str) -> Path:
    return runs_root / run_id / "manifest.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {"entries": []}


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


async def _run_one_debate(
    prompt: str,
    elders: dict[ElderId, ElderPort],
    store: JsonFileStore,
    max_rounds: int,
    synthesiser: ElderId,
) -> str:
    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )
    svc = DebateService(
        elders=elders, store=store, clock=SystemClock(), bus=InMemoryBus(),
    )
    await svc.run_round(debate)  # R1
    await svc.run_round(debate)  # R2
    while (
        len(debate.rounds) < max_rounds
        and not svc.rules.is_converged(debate.rounds[-1])
    ):
        await svc.run_round(debate)
    await svc.synthesize(debate, by=synthesiser)
    return debate.id


async def run_probe(
    *,
    rosters: tuple[RosterSpec, ...],
    prompts: list[CorpusPrompt],
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    elder_factory: ElderFactory,
    max_rounds: int,
    synthesiser: ElderId,
) -> Path:
    """Run the debates and write the manifest. Returns the manifest path."""
    manifest_path = _manifest_path(runs_root, run_id)
    manifest = _load_manifest(manifest_path)
    done: set[tuple[str, str]] = {
        (e["roster"], e["prompt_id"]) for e in manifest["entries"]
    }
    store = JsonFileStore(root=debate_store_root)

    for roster in rosters:
        pending = [p for p in prompts if (roster.name, p.id) not in done]
        if not pending:
            continue
        elders = elder_factory(roster)
        for prompt in pending:
            debate_id = await _run_one_debate(
                prompt=prompt.prompt, elders=elders, store=store,
                max_rounds=max_rounds, synthesiser=synthesiser,
            )
            manifest["entries"].append({
                "roster": roster.name,
                "prompt_id": prompt.id,
                "debate_id": debate_id,
            })
            _write_manifest(manifest_path, manifest)  # persist incrementally
    return manifest_path
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_runner.py -v`
Expected: 2 passed. (If the second test fails because the FakeElder exhausts replies on re-import, confirm the `calls["n"] == 1` branch skips `elder_factory` entirely when manifest already covers all pairs.)

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/runner.py tests/unit/test_homogenisation_runner.py
git commit -m "feat(homogenisation): phase-1 runner with resumable manifest"
```

---

### Task 8: Scorer (phase 2) — judge calls + aggregation

**Files:**
- Create: `council/experiments/homogenisation/scorer.py`
- Test: `tests/unit/test_homogenisation_scorer.py`

Reads the manifest + saved debates, calls the three judges, aggregates into per-debate score rows and per-roster summaries, writes `scores.json`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_homogenisation_scorer.py`:

```python
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from council.experiments.homogenisation.scorer import (
    RosterSummary,
    _binomial_ci_90,
    _summarise_rosters,
    score_probe,
)


def test_binomial_ci_90_returns_symmetric_tight_interval_for_5050() -> None:
    lo, hi = _binomial_ci_90(successes=5, n=10)
    assert 0.2 <= lo <= 0.45
    assert 0.55 <= hi <= 0.8
    assert math.isclose((lo + hi) / 2, 0.5, abs_tol=0.05)


def test_binomial_ci_90_handles_zero_n() -> None:
    lo, hi = _binomial_ci_90(successes=0, n=0)
    assert lo == 0.0 and hi == 1.0


def test_summarise_rosters_computes_mean_median_rate() -> None:
    rows = [
        {"roster": "r1", "r1_jaccard": 0.4, "preference_winner": "synthesis"},
        {"roster": "r1", "r1_jaccard": 0.6, "preference_winner": "best_r1"},
        {"roster": "r1", "r1_jaccard": 0.8, "preference_winner": "tie"},
        {"roster": "r2", "r1_jaccard": 0.1, "preference_winner": "synthesis"},
    ]
    summaries = _summarise_rosters(rows)
    by_name = {s.roster: s for s in summaries}
    assert by_name["r1"].n_debates == 3
    assert math.isclose(by_name["r1"].mean_r1_jaccard, 0.6, abs_tol=1e-9)
    assert math.isclose(by_name["r1"].median_r1_jaccard, 0.6, abs_tol=1e-9)
    # 1 synth + 1 tie (=0.5) + 0 = 1.5 / 3
    assert math.isclose(by_name["r1"].preference_rate, 0.5, abs_tol=1e-9)
    assert by_name["r2"].preference_rate == 1.0
```

Note: this task tests only the aggregation pure functions. The full `score_probe` end-to-end is exercised in the e2e test (Task 10).

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/unit/test_homogenisation_scorer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement scorer + aggregation**

Create `council/experiments/homogenisation/scorer.py`:

```python
"""Phase 2 of the homogenisation probe: call the three judges per
debate, aggregate per-debate scores into per-roster summaries, write
scores.json.

Idempotent: if a scores.json already has an entry for a debate_id, the
entry is preserved and its judge calls are skipped on re-run.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from council.adapters.storage.json_file import JsonFileStore
from council.domain.models import Debate, ElderId
from council.domain.ports import ElderPort
from council.experiments.homogenisation.judges import (
    judge_best_r1,
    judge_claim_overlap,
    judge_preference,
)


@dataclass(frozen=True)
class DebateScoreRow:
    debate_id: str
    roster: str
    prompt_id: str
    r1_jaccard: float
    preference_winner: str  # "synthesis" | "best_r1" | "tie"


@dataclass(frozen=True)
class RosterSummary:
    roster: str
    n_debates: int
    mean_r1_jaccard: float
    median_r1_jaccard: float
    preference_rate: float
    preference_ci_lo: float
    preference_ci_hi: float


_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("claude", "gemini", "chatgpt")


def _r1_texts(debate: Debate) -> dict[ElderId, str]:
    if not debate.rounds:
        return {}
    r1 = debate.rounds[0]
    return {t.elder: (t.answer.text or "") for t in r1.turns}


async def _score_one_debate(
    debate: Debate, judge_port: ElderPort, rng: random.Random
) -> tuple[float, str]:
    """Run the three judges on one debate, return (r1_jaccard, winner)."""
    r1 = _r1_texts(debate)
    pairs = list(combinations(_ELDER_ORDER, 2))
    jaccards: list[float] = []
    for a, b in pairs:
        obs = await judge_claim_overlap(
            question=debate.prompt, answer_a=r1[a], answer_b=r1[b],
            judge_port=judge_port,
        )
        jaccards.append(obs.jaccard)
    mean_j = statistics.fmean(jaccards) if jaccards else 0.0

    answers = tuple(r1[e] for e in _ELDER_ORDER)
    best = await judge_best_r1(
        question=debate.prompt, answers=answers, judge_port=judge_port,
    )
    best_text = answers[best.best_index - 1]
    synth_text = debate.synthesis.text if debate.synthesis else ""
    pref = await judge_preference(
        question=debate.prompt, best_r1=best_text, synthesis=synth_text,
        judge_port=judge_port, rng=rng,
    )
    return mean_j, pref.winner


def _binomial_ci_90(*, successes: int, n: int) -> tuple[float, float]:
    """Wilson-approximation 90% CI for a binomial proportion.

    Uses the normal-approximation Wilson form; n=0 returns (0, 1).
    """
    if n == 0:
        return (0.0, 1.0)
    z = 1.6448536269514722  # 90% two-sided
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _summarise_rosters(rows: list[dict[str, Any]]) -> list[RosterSummary]:
    by_roster: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_roster.setdefault(r["roster"], []).append(r)
    out: list[RosterSummary] = []
    for name, group in sorted(by_roster.items()):
        jaccards = [g["r1_jaccard"] for g in group]
        # Synthesis wins count as 1, ties count as 0.5, losses 0.
        synth_score = sum(
            1.0 if g["preference_winner"] == "synthesis"
            else 0.5 if g["preference_winner"] == "tie" else 0.0
            for g in group
        )
        rate = synth_score / len(group) if group else 0.0
        # CI uses successes = round(synth_score), n = len(group) —
        # ties inflate the successes count by 0.5 which we round to
        # the nearest integer for the binomial approximation.
        successes = round(synth_score)
        lo, hi = _binomial_ci_90(successes=successes, n=len(group))
        out.append(RosterSummary(
            roster=name, n_debates=len(group),
            mean_r1_jaccard=statistics.fmean(jaccards) if jaccards else 0.0,
            median_r1_jaccard=statistics.median(jaccards) if jaccards else 0.0,
            preference_rate=rate, preference_ci_lo=lo, preference_ci_hi=hi,
        ))
    return out


async def score_probe(
    *,
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    judge_port: ElderPort,
    seed: int = 0,
) -> Path:
    """Run judges across the manifest, aggregate, write scores.json."""
    manifest_path = runs_root / run_id / "manifest.json"
    scores_path = runs_root / run_id / "scores.json"
    manifest = json.loads(manifest_path.read_text())
    existing: dict[str, dict[str, Any]] = {}
    if scores_path.exists():
        data = json.loads(scores_path.read_text())
        existing = {r["debate_id"]: r for r in data.get("rows", [])}
    store = JsonFileStore(root=debate_store_root)
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        debate_id = entry["debate_id"]
        if debate_id in existing:
            rows.append(existing[debate_id])
            continue
        debate = store.load(debate_id)
        r1_jaccard, winner = await _score_one_debate(debate, judge_port, rng)
        row = {
            "debate_id": debate_id, "roster": entry["roster"],
            "prompt_id": entry["prompt_id"],
            "r1_jaccard": r1_jaccard, "preference_winner": winner,
        }
        rows.append(row)
    summaries = [asdict(s) for s in _summarise_rosters(rows)]
    scores_path.write_text(json.dumps(
        {"rows": rows, "summaries": summaries}, indent=2,
    ))
    return scores_path
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_scorer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/scorer.py tests/unit/test_homogenisation_scorer.py
git commit -m "feat(homogenisation): phase-2 scorer with Jaccard + Wilson CI"
```

---

### Task 9: Reporter (phase 3)

**Files:**
- Create: `council/experiments/homogenisation/reporter.py`
- Test: `tests/unit/test_homogenisation_reporter.py`

Pure data transform: `scores.json + corpus + rosters` → markdown. No I/O other than reading scores and writing the report.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_homogenisation_reporter.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.reporter import render_report
from council.experiments.homogenisation.rosters import RosterSpec


def _fixture_scores() -> dict[str, object]:
    return {
        "rows": [
            {"debate_id": "d1", "roster": "homogeneous", "prompt_id": "p1",
             "r1_jaccard": 0.8, "preference_winner": "synthesis"},
            {"debate_id": "d2", "roster": "mixed_baseline", "prompt_id": "p1",
             "r1_jaccard": 0.4, "preference_winner": "best_r1"},
        ],
        "summaries": [
            {"roster": "homogeneous", "n_debates": 1, "mean_r1_jaccard": 0.8,
             "median_r1_jaccard": 0.8, "preference_rate": 1.0,
             "preference_ci_lo": 0.0, "preference_ci_hi": 1.0},
            {"roster": "mixed_baseline", "n_debates": 1, "mean_r1_jaccard": 0.4,
             "median_r1_jaccard": 0.4, "preference_rate": 0.0,
             "preference_ci_lo": 0.0, "preference_ci_hi": 1.0},
        ],
    }


def test_render_report_contains_all_key_sections(tmp_path: Path) -> None:
    scores_path = tmp_path / "scores.json"
    scores_path.write_text(json.dumps(_fixture_scores()))
    corpus = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    rosters = (
        RosterSpec(name="homogeneous", models={"claude": "m1", "gemini": "m1", "chatgpt": "m1"}),
        RosterSpec(name="mixed_baseline", models={"claude": "m2", "gemini": "m3", "chatgpt": "m4"}),
    )
    md = render_report(
        scores_path=scores_path, corpus=corpus, rosters=rosters, run_id="2026-04-19-test",
    )
    for section in [
        "# Model homogenisation probe",
        "## Question",
        "## Rosters tested",
        "## Corpus",
        "### Metric 1",
        "### Metric 2",
        "## Interpretation",
        "## Caveats",
        "## Appendix",
    ]:
        assert section in md, f"missing section: {section!r}"


def test_render_report_interprets_small_diversity_gap() -> None:
    scores_path_input = _fixture_scores()
    # Shrink the gap: homogeneous 0.60, mixed 0.58 → diversity negligible.
    scores_path_input["summaries"][0]["mean_r1_jaccard"] = 0.60
    scores_path_input["summaries"][1]["mean_r1_jaccard"] = 0.58
    from pathlib import Path as _P
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p = _P(td) / "scores.json"
        p.write_text(json.dumps(scores_path_input))
        corpus = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
        rosters = (
            RosterSpec(name="homogeneous", models={"claude": "m1", "gemini": "m1", "chatgpt": "m1"}),
            RosterSpec(name="mixed_baseline", models={"claude": "m2", "gemini": "m3", "chatgpt": "m4"}),
        )
        md = render_report(
            scores_path=p, corpus=corpus, rosters=rosters, run_id="2026-04-19-test",
        )
    assert "negligible" in md.lower() or "doesn't matter" in md.lower()
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/unit/test_homogenisation_reporter.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement reporter**

Create `council/experiments/homogenisation/reporter.py`:

```python
"""Phase 3 of the homogenisation probe: render the markdown report
from scored data.

Pure data transform. The heavy lifting is the interpretation table —
it converts per-roster summaries into a plain-English verdict using
the thresholds documented in the spec. Everything else is formatting.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.rosters import RosterSpec

_QUESTION_VERBATIM = (
    "All three current elders (Claude Opus, Gemini Pro, GPT-5) are trained "
    "on heavily overlapping web data and RLHF'd toward similar behaviours. "
    "Does the tool's value come from model diversity, from the debate "
    "protocol, from both, or from neither?"
)


def _interpret(summaries: list[dict[str, Any]]) -> list[str]:
    """Turn per-roster summaries into verdict bullets."""
    by_name = {s["roster"]: s for s in summaries}
    bullets: list[str] = []
    hom = by_name.get("homogeneous")
    mix = by_name.get("mixed_baseline")
    sub = by_name.get("substituted")

    if hom and mix:
        gap = hom["mean_r1_jaccard"] - mix["mean_r1_jaccard"]
        if gap < 0.05:
            bullets.append(
                f"Model diversity produces negligible R1 variance on this corpus "
                f"(homogeneous−mixed Jaccard gap = {gap:+.3f}; threshold 0.05)."
            )
        else:
            bullets.append(
                f"Mixed roster has measurably lower R1 claim-overlap than the "
                f"homogeneous control (gap = {gap:+.3f}) — model diversity matters."
            )
    if mix and sub:
        gap = mix["mean_r1_jaccard"] - sub["mean_r1_jaccard"]
        if gap > 0.10:
            bullets.append(
                f"Open-weights substitution adds meaningful diversity beyond the "
                f"same-lineage trio (mixed−substituted gap = {gap:+.3f})."
            )
        else:
            bullets.append(
                f"Open-weights substitution does not measurably widen diversity "
                f"(mixed−substituted gap = {gap:+.3f}; threshold 0.10)."
            )
    if hom and mix:
        pref_gap = mix["preference_rate"] - hom["preference_rate"]
        if pref_gap > 0.10:
            bullets.append(
                f"Tool's value appears to depend on both mechanisms — mixed "
                f"synthesis-preference exceeds homogeneous by {pref_gap:+.3f}."
            )
        elif abs(pref_gap) <= 0.10:
            bullets.append(
                f"Debate protocol alone does most of the work — homogeneous "
                f"and mixed preference rates are within ±0.10 ({pref_gap:+.3f})."
            )
    return bullets


def _rosters_table(rosters: tuple[RosterSpec, ...]) -> str:
    rows = ["| Roster | claude slot | gemini slot | chatgpt slot |", "|---|---|---|---|"]
    for r in rosters:
        rows.append(
            f"| `{r.name}` | `{r.models['claude']}` | "
            f"`{r.models['gemini']}` | `{r.models['chatgpt']}` |"
        )
    return "\n".join(rows)


def _corpus_table(corpus: list[CorpusPrompt]) -> str:
    rows = ["| id | shape | prompt |", "|---|---|---|"]
    for p in corpus:
        rows.append(f"| `{p.id}` | {p.shape} | {p.prompt} |")
    return "\n".join(rows)


def _jaccard_table(summaries: list[dict[str, Any]]) -> str:
    rows = ["| Roster | n | mean R1 Jaccard | median |", "|---|---|---|---|"]
    for s in summaries:
        rows.append(
            f"| `{s['roster']}` | {s['n_debates']} | "
            f"{s['mean_r1_jaccard']:.3f} | {s['median_r1_jaccard']:.3f} |"
        )
    return "\n".join(rows)


def _preference_table(summaries: list[dict[str, Any]]) -> str:
    rows = ["| Roster | n | pref rate | 90% CI |", "|---|---|---|---|"]
    for s in summaries:
        rows.append(
            f"| `{s['roster']}` | {s['n_debates']} | {s['preference_rate']:.3f} | "
            f"[{s['preference_ci_lo']:.3f}, {s['preference_ci_hi']:.3f}] |"
        )
    return "\n".join(rows)


def _appendix(rows: list[dict[str, Any]]) -> str:
    lines = ["| debate | roster | prompt | R1 Jaccard | winner |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| `{r['debate_id'][:8]}` | {r['roster']} | {r['prompt_id']} | "
            f"{r['r1_jaccard']:.3f} | {r['preference_winner']} |"
        )
    return "\n".join(lines)


def render_report(
    *,
    scores_path: Path,
    corpus: list[CorpusPrompt],
    rosters: tuple[RosterSpec, ...],
    run_id: str,
) -> str:
    data = json.loads(scores_path.read_text())
    rows: list[dict[str, Any]] = data["rows"]
    summaries: list[dict[str, Any]] = data["summaries"]
    date_str = _dt.date.today().isoformat()
    verdict_bullets = _interpret(summaries)
    verdict_md = "\n".join(f"- {b}" for b in verdict_bullets) or "- (no data)"

    return f"""# Model homogenisation probe — {date_str}

Run id: `{run_id}`

## Question

{_QUESTION_VERBATIM}

## Rosters tested

{_rosters_table(rosters)}

## Corpus

{_corpus_table(corpus)}

## Results

### Metric 1 — R1 claim-overlap (Jaccard)

Lower = more diverse. Pairwise Jaccard averaged per debate, then averaged across corpus per roster.

{_jaccard_table(summaries)}

### Metric 2 — Synthesis-vs-best-R1 preference

Fraction of debates where the judge preferred the final synthesis over the strongest R1 answer. Ties counted as 0.5. 90% binomial (Wilson) CI.

{_preference_table(summaries)}

## Interpretation

{verdict_md}

## Caveats

- Small n (8 prompts); results directional, not significance-tested.
- Single judge model (gemini-2.5-flash). Internally consistent; absolute numbers not portable to other judges.
- One open-weights substitute (Llama-3.1-70B), one homogeneous model (gpt-5-mini). Other choices could give different numbers.
- gemini slot substituted; other slots not swept.
- Round cap 6 may truncate debates; reported, not mitigated.
- Judge family proximity — gemini-flash may bias toward gemini-slot content in mixed/substituted rosters.
- Persona priming: homogeneous elders still see peers labelled as "Claude"/"Gemini"/"ChatGPT" via the existing prompt pack, so this is not a clean model-equivalence test — it is the operational behaviour a user configuring 3× same-model would see.

## Appendix A — per-debate details

{_appendix(rows)}

## Appendix B — run metadata

Run id: `{run_id}` · Report generated: {date_str}
"""
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_homogenisation_reporter.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add council/experiments/homogenisation/reporter.py tests/unit/test_homogenisation_reporter.py
git commit -m "feat(homogenisation): phase-3 markdown reporter with interpretation"
```

---

### Task 10: CLI entry + end-to-end smoke test

**Files:**
- Create: `scripts/homogenisation_probe.py`
- Create: `tests/e2e/test_homogenisation_probe.py`

CLI has three subcommands: `run`, `score`, `report`. Each wraps the corresponding module's entry function and picks up the `OPENROUTER_API_KEY` from `load_config()` for the real-network paths.

- [ ] **Step 1: Write the failing e2e test**

Create `tests/e2e/test_homogenisation_probe.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from council.adapters.elders.fake import FakeElder
from council.domain.models import ElderId
from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.reporter import render_report
from council.experiments.homogenisation.rosters import RosterSpec
from council.experiments.homogenisation.runner import run_probe
from council.experiments.homogenisation.scorer import score_probe


def _scripted_debate_replies() -> list[str]:
    return [
        "R1 answer",
        "CONVERGED: no\n\nR2 answer\n\nQUESTIONS:\n@chatgpt why?",
        "CONVERGED: yes\n\nR3 final",
        "Synthesised answer.",
        "Report body.", "Narrative audit body.",
    ]


def _elder_factory(_spec: RosterSpec) -> dict[ElderId, Any]:
    return {
        slot: FakeElder(elder_id=slot, replies=_scripted_debate_replies())
        for slot in ("claude", "gemini", "chatgpt")
    }


def _judge_port() -> FakeElder:
    # Scripted judge replies — 3 claim-overlap + 1 best-R1 + 1 preference
    # per debate; one roster × one prompt = 5 total.
    return FakeElder(
        elder_id="claude",
        replies=[
            "shared_count: 3\na_only_count: 1\nb_only_count: 1\nnote: x\n",
            "shared_count: 3\na_only_count: 1\nb_only_count: 1\nnote: y\n",
            "shared_count: 3\na_only_count: 1\nb_only_count: 1\nnote: z\n",
            "best: 1\nreason: shortest.\n",
            "winner: X\nreason: cleaner.\n",
        ],
    )


@pytest.mark.asyncio
async def test_full_probe_pipeline_end_to_end(tmp_path: Path) -> None:
    corpus = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    rosters = (RosterSpec(
        name="mixed_baseline",
        models={"claude": "a/a", "gemini": "b/b", "chatgpt": "c/c"},
    ),)
    run_id = "2026-04-19-e2e"

    # Phase 1.
    await run_probe(
        rosters=rosters, prompts=corpus, run_id=run_id,
        runs_root=tmp_path, debate_store_root=tmp_path / "debates",
        elder_factory=_elder_factory, max_rounds=3, synthesiser="claude",
    )
    manifest_path = tmp_path / run_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["entries"]) == 1

    # Phase 2.
    scores_path = await score_probe(
        run_id=run_id, runs_root=tmp_path, debate_store_root=tmp_path / "debates",
        judge_port=_judge_port(),
    )
    assert scores_path.exists()
    data = json.loads(scores_path.read_text())
    assert len(data["rows"]) == 1
    assert data["rows"][0]["roster"] == "mixed_baseline"

    # Phase 3.
    md = render_report(
        scores_path=scores_path, corpus=corpus, rosters=rosters, run_id=run_id,
    )
    assert "# Model homogenisation probe" in md
    assert "mixed_baseline" in md
```

- [ ] **Step 2: Run the e2e test, verify it passes with all prior tasks merged**

Run: `pytest tests/e2e/test_homogenisation_probe.py -v`
Expected: 1 passed. This validates phases 1-3 wire together.

- [ ] **Step 3: Implement the CLI**

Create `scripts/homogenisation_probe.py`:

```python
#!/usr/bin/env python3
"""CLI entrypoint for the homogenisation probe.

    python scripts/homogenisation_probe.py run --run-id 2026-04-19-abcd
    python scripts/homogenisation_probe.py score --run-id 2026-04-19-abcd
    python scripts/homogenisation_probe.py report --run-id 2026-04-19-abcd

Requires OPENROUTER_API_KEY (env or ~/.council/config.toml).
See docs/superpowers/specs/2026-04-19-issue-11-homogenisation-test-design.md.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from datetime import date
from pathlib import Path

# Make the `council` package importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council.adapters.elders.openrouter import OpenRouterAdapter  # noqa: E402
from council.app.config import load_config  # noqa: E402
from council.experiments.homogenisation.corpus import load_corpus  # noqa: E402
from council.experiments.homogenisation.reporter import render_report  # noqa: E402
from council.experiments.homogenisation.rosters import (  # noqa: E402
    ROSTERS,
    build_roster_elders,
)
from council.experiments.homogenisation.runner import run_probe  # noqa: E402
from council.experiments.homogenisation.scorer import score_probe  # noqa: E402

DEFAULT_JUDGE_MODEL = "google/gemini-2.5-flash"
DEFAULT_RUNS_ROOT = Path("runs")
DEFAULT_CORPUS = Path("scripts/homogenisation_corpus.json")
DEFAULT_REPORTS_ROOT = Path("docs/experiments")


def _new_run_id() -> str:
    return f"{date.today().isoformat()}-{secrets.token_hex(2)}"


def _require_key() -> str:
    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; set the env var or put it in "
            "~/.council/config.toml before running the probe."
        )
    return config.openrouter_api_key


async def _cmd_run(args: argparse.Namespace) -> None:
    api_key = _require_key()
    prompts = load_corpus(Path(args.corpus))

    def factory(spec):  # noqa: ANN001 — RosterSpec
        return build_roster_elders(spec, api_key=api_key)

    manifest_path = await run_probe(
        rosters=ROSTERS, prompts=prompts, run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        elder_factory=factory,
        max_rounds=args.max_rounds, synthesiser="claude",
    )
    print(f"Run complete. Manifest: {manifest_path}")


async def _cmd_score(args: argparse.Namespace) -> None:
    api_key = _require_key()
    judge = OpenRouterAdapter(
        elder_id="claude", model=args.judge_model, api_key=api_key,
    )
    path = await score_probe(
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        judge_port=judge, seed=args.seed,
    )
    print(f"Scoring complete. Scores: {path}")


def _cmd_report(args: argparse.Namespace) -> None:
    prompts = load_corpus(Path(args.corpus))
    scores_path = Path(args.runs_root) / args.run_id / "scores.json"
    md = render_report(
        scores_path=scores_path, corpus=prompts, rosters=ROSTERS, run_id=args.run_id,
    )
    out = Path(args.reports_root) / f"{args.run_id}-homogenisation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"Report written: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="homogenisation_probe")
    parser.add_argument(
        "--runs-root", default=str(DEFAULT_RUNS_ROOT),
        help=f"Where manifest/scores live (default: {DEFAULT_RUNS_ROOT})",
    )
    parser.add_argument(
        "--corpus", default=str(DEFAULT_CORPUS),
        help=f"Corpus JSON (default: {DEFAULT_CORPUS})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Phase 1 — run debates across rosters")
    run_p.add_argument("--run-id", default=None)
    run_p.add_argument("--max-rounds", type=int, default=6)

    score_p = sub.add_parser("score", help="Phase 2 — call judges, aggregate")
    score_p.add_argument("--run-id", required=True)
    score_p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    score_p.add_argument("--seed", type=int, default=0)

    rep_p = sub.add_parser("report", help="Phase 3 — render markdown report")
    rep_p.add_argument("--run-id", required=True)
    rep_p.add_argument("--reports-root", default=str(DEFAULT_REPORTS_ROOT))

    args = parser.parse_args()

    if args.cmd == "run":
        if args.run_id is None:
            args.run_id = _new_run_id()
            print(f"New run id: {args.run_id}")
        asyncio.run(_cmd_run(args))
    elif args.cmd == "score":
        asyncio.run(_cmd_score(args))
    elif args.cmd == "report":
        _cmd_report(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke-test the CLI surface**

Run: `python scripts/homogenisation_probe.py --help`
Expected: shows `run`, `score`, `report` subcommands.

Run: `python scripts/homogenisation_probe.py run --help`
Expected: shows `--run-id`, `--max-rounds` flags.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all new tests pass; no existing tests regress.

- [ ] **Step 6: Commit**

```bash
git add scripts/homogenisation_probe.py tests/e2e/test_homogenisation_probe.py
git commit -m "feat(homogenisation): CLI entrypoint + e2e pipeline smoke test"
```

---

## Post-implementation checklist (not part of tasks)

After all 10 tasks commit cleanly:

1. Add `runs/` to `.gitignore` (generated, per-run artifacts).
2. Add `docs/experiments/` to `.gitignore` *or* decide to commit interesting reports ad hoc.
3. Consider a one-line `README` note pointing to the spec + a usage example.
4. Actually run the probe once with real API calls — the *result* of this experiment is the whole point, not the script. Budget ~$10. Inspect the generated report and check that every section renders with real data (there will almost certainly be surprises — unparsed judge outputs, edge cases in the interpretation thresholds). Iterate on the corpus or thresholds if results are ambiguous.
