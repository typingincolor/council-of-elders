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
