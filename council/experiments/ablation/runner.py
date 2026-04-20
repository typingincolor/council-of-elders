"""Debate-depth ablation runner.

Purpose: isolate whether the debate format (R2 cross-examination, R3+
convergence) adds value on top of R1-only-then-synthesise. Motivated
by the Stage 11 result (synthesis never beat best-R1 across any roster
configuration); see
``docs/experiments/2026-04-20-f294-results.md``.

Design: fix the roster (diff_model: sonnet + llama-70b + gpt-5) and
the corpus (homogenisation's 8 prompts). Vary *only* the number of
rounds before synthesis. Each variant's name goes into the manifest's
``roster`` field so the existing
``council.experiments.diversity_split.scorer.score_probe_multi``
consumes the output unchanged.

Variants:
- ``r1_only``    — R1 only, then synthesise. Ensembling-as-synthesis.
- ``r1_r2``      — R1 + R2 cross-exam, then synthesise.
- ``full_debate``— R1 + R2 + R3 (max_rounds=3), then synthesise.

If R1-only synthesis matches or beats full_debate synthesis, the
debate rounds are negative-value.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.storage.json_file import JsonFileStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate, ElderId
from council.domain.ports import ElderPort
from council.domain.roster import RosterSpec
from council.experiments.homogenisation.corpus import CorpusPrompt


@dataclass(frozen=True)
class Variant:
    """One depth setting for the ablation.

    ``rounds_before_synthesis`` — 1 for R1-only, 2 for R1+R2, 3 for full
    debate. The runner invokes ``run_round`` exactly this many times
    before calling ``synthesize``. Convergence-based early termination
    is NOT used: each variant runs a fixed depth so the comparison is
    clean.
    """

    name: str
    rounds_before_synthesis: int


VARIANTS: tuple[Variant, ...] = (
    Variant(name="r1_only", rounds_before_synthesis=1),
    Variant(name="r1_r2", rounds_before_synthesis=2),
    Variant(name="full_debate", rounds_before_synthesis=3),
)


ElderFactory = Callable[[], dict[ElderId, ElderPort]]

_SYNTHESISER_ROTATION: tuple[ElderId, ...] = ("ada", "kai", "mei")


def _manifest_path(runs_root: Path, run_id: str) -> Path:
    return runs_root / run_id / "manifest.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {"entries": []}


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(tmp, path)


async def _run_one_debate(
    *,
    prompt: str,
    roster: RosterSpec,
    elders: dict[ElderId, ElderPort],
    store: JsonFileStore,
    rounds_before_synthesis: int,
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
        elders=elders,
        store=store,
        clock=SystemClock(),
        bus=InMemoryBus(),
    )
    for _ in range(rounds_before_synthesis):
        await svc.run_round(debate)
    await svc.synthesize(debate, by=synthesiser)
    return debate.id


async def run_ablation(
    *,
    variants: tuple[Variant, ...],
    roster: RosterSpec,
    prompts: list[CorpusPrompt],
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    elder_factory: ElderFactory,
) -> Path:
    """Run the depth-ablation variants and write the manifest.

    Idempotent at (variant, prompt) pair granularity — re-running with
    the same ``run_id`` resumes from the first incomplete pair. Manifest
    rows use ``variant.name`` as the ``roster`` field so the existing
    diversity_split scorer consumes them without modification.
    """
    manifest_path = _manifest_path(runs_root, run_id)
    manifest = _load_manifest(manifest_path)
    done: set[tuple[str, str]] = {(e["roster"], e["prompt_id"]) for e in manifest["entries"]}
    store = JsonFileStore(root=debate_store_root)

    for variant in variants:
        pending = [p for p in prompts if (variant.name, p.id) not in done]
        if not pending:
            continue
        elders = elder_factory()
        for prompt in pending:
            prompt_index = prompts.index(prompt)
            synthesiser: ElderId = _SYNTHESISER_ROTATION[prompt_index % 3]
            debate_id = await _run_one_debate(
                prompt=prompt.prompt,
                roster=roster,
                elders=elders,
                store=store,
                rounds_before_synthesis=variant.rounds_before_synthesis,
                synthesiser=synthesiser,
            )
            manifest["entries"].append(
                {
                    "roster": variant.name,
                    "prompt_id": prompt.id,
                    "debate_id": debate_id,
                    "synthesiser": synthesiser,
                }
            )
            _write_manifest(manifest_path, manifest)
    return manifest_path
