"""Runner for the 2×2 diversity-split experiment.

Structured the same way as ``council.experiments.homogenisation.runner``
so results can be scored with the same judges and compared directly.
One debate per (condition, prompt) pair. Synthesiser rotates across
prompts for fairness, matching the homogenisation runner.

Resumes at pair granularity via the manifest on disk — same semantics
as the homogenisation runner: if a pair is already in the manifest it
is skipped.
"""
from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.storage.json_file import JsonFileStore
from council.domain.debate_service import DebateService
from council.domain.models import Debate, ElderId
from council.domain.ports import ElderPort
from council.experiments.diversity_split.conditions import Condition
from council.experiments.homogenisation.corpus import CorpusPrompt

ElderFactory = Callable[[Condition], dict[ElderId, ElderPort]]

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
    condition: Condition,
    elders: dict[ElderId, ElderPort],
    store: JsonFileStore,
    max_rounds: int,
    synthesiser: ElderId,
) -> str:
    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=condition.pack,
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
    await svc.run_round(debate)  # R1
    await svc.run_round(debate)  # R2
    while len(debate.rounds) < max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
        await svc.run_round(debate)
    await svc.synthesize(debate, by=synthesiser)
    return debate.id


async def run_experiment(
    *,
    conditions: tuple[Condition, ...],
    prompts: list[CorpusPrompt],
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    elder_factory: ElderFactory,
    max_rounds: int,
) -> Path:
    """Run all (condition, prompt) pairs, writing the manifest.

    The manifest uses ``roster`` as its column name (not ``condition``)
    so that ``council.experiments.homogenisation.scorer.score_probe``
    can consume it unchanged. The condition name occupies the roster
    field — homogenisation and diversity_split share an output format.
    """
    if max_rounds < 2:
        raise ValueError("max_rounds must be at least 2 (R1+R2 are mandatory)")
    manifest_path = _manifest_path(runs_root, run_id)
    manifest = _load_manifest(manifest_path)
    done: set[tuple[str, str]] = {
        (e["roster"], e["prompt_id"]) for e in manifest["entries"]
    }
    store = JsonFileStore(root=debate_store_root)

    for condition in conditions:
        pending = [p for p in prompts if (condition.name, p.id) not in done]
        if not pending:
            continue
        elders = elder_factory(condition)
        for prompt in pending:
            prompt_index = prompts.index(prompt)
            synthesiser: ElderId = _SYNTHESISER_ROTATION[prompt_index % 3]
            debate_id = await _run_one_debate(
                prompt=prompt.prompt,
                condition=condition,
                elders=elders,
                store=store,
                max_rounds=max_rounds,
                synthesiser=synthesiser,
            )
            manifest["entries"].append(
                {
                    "roster": condition.name,  # field re-used for scorer compat
                    "prompt_id": prompt.id,
                    "debate_id": debate_id,
                    "synthesiser": synthesiser,
                }
            )
            _write_manifest(manifest_path, manifest)
    return manifest_path
