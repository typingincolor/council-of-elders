"""Phase 1 of the homogenisation probe: run one debate per (roster,
prompt) pair and record debate IDs in a manifest file.

Debates are persisted via the existing JsonFileStore so later phases
can read full debate objects. Already-completed (roster, prompt)
pairs are skipped, and the elder-factory is not called for rosters
with no pending work — this keeps restart cost-safe (no HTTP clients
constructed, no accidental credit use).

Resumption is at PAIR granularity, not round granularity: if a debate
crashes partway through (e.g. a 429 or timeout in round 2), the
partial debate JSON remains on disk but has no manifest entry, and a
restart will re-run the pair from scratch. The earlier rounds' API
spend is re-paid.

Failure policy is FAIL-FAST: the first unhandled exception from
_run_one_debate propagates up through run_probe, halting further
work. The caller is expected to restart manually after investigating.
This is deliberate — surfacing transient errors is more useful than
silently skipping prompts in a research experiment.
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(tmp, path)


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


_SYNTHESISER_ROTATION: tuple[ElderId, ...] = ("claude", "gemini", "chatgpt")


async def run_probe(
    *,
    rosters: tuple[RosterSpec, ...],
    prompts: list[CorpusPrompt],
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    elder_factory: ElderFactory,
    max_rounds: int,
) -> Path:
    """Run the debates and write the manifest. Returns the manifest path."""
    if max_rounds < 2:
        raise ValueError("max_rounds must be at least 2 (R1+R2 are mandatory)")
    manifest_path = _manifest_path(runs_root, run_id)
    manifest = _load_manifest(manifest_path)
    done: set[tuple[str, str]] = {(e["roster"], e["prompt_id"]) for e in manifest["entries"]}
    store = JsonFileStore(root=debate_store_root)

    for roster in rosters:
        pending = [p for p in prompts if (roster.name, p.id) not in done]
        if not pending:
            continue
        elders = elder_factory(roster)
        for prompt in pending:
            prompt_index = prompts.index(prompt)
            synthesiser: ElderId = _SYNTHESISER_ROTATION[prompt_index % 3]
            debate_id = await _run_one_debate(
                prompt=prompt.prompt,
                elders=elders,
                store=store,
                max_rounds=max_rounds,
                synthesiser=synthesiser,
            )
            manifest["entries"].append(
                {
                    "roster": roster.name,
                    "prompt_id": prompt.id,
                    "debate_id": debate_id,
                    "synthesiser": synthesiser,
                }
            )
            _write_manifest(manifest_path, manifest)  # persist incrementally
    return manifest_path
