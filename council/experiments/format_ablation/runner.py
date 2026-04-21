"""Format-ablation runner.

Tests two independent interventions against the r1_only + current-
synthesis-prompt baseline (established by the 2026-04-20-226f ablation):

- ``alt_synth``      — R1 only, alt (free-form) synthesis prompt.
- ``silent_revise``  — R1 + silent-revise R2 (elders privately revise
                       their own answer after reading peers), current
                       synthesis prompt.

Variants are independent comparisons against baseline; not a 2×2. The
question answered is "which of these two format changes helps, if
either?", not "what's the interaction effect?".

Debates persist via ``JsonFileStore`` using the same manifest format
as the other experiments so
``council.experiments.diversity_split.scorer.score_probe_multi``
consumes the output unchanged.
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
from council.domain.prompting import build_alt_synthesis
from council.domain.roster import RosterSpec
from council.domain.rules import DebateRules, DefaultRules, SilentReviseRules
from council.experiments.homogenisation.corpus import CorpusPrompt


@dataclass(frozen=True)
class FormatVariant:
    """One format-ablation cell.

    ``rules_factory`` builds the DebateRules instance used for this
    variant's debate rounds. ``rounds`` is the number of rounds to run
    before synthesis. ``use_alt_synthesis_prompt`` selects between the
    default Answer/Why/Disagreements synthesis prompt (False) and the
    free-form alternative (True).
    """

    name: str
    rules_factory: Callable[[], DebateRules]
    rounds: int
    use_alt_synthesis_prompt: bool


VARIANTS: tuple[FormatVariant, ...] = (
    # Baseline re-run so all three cells are scored with the same
    # fixed scorer in a single manifest. We already have r1_only data
    # from 2026-04-20-226f but running it again here costs only ~$0.10
    # and ensures the three variants are apples-to-apples.
    FormatVariant(
        name="baseline_r1_only",
        rules_factory=DefaultRules,
        rounds=1,
        use_alt_synthesis_prompt=False,
    ),
    FormatVariant(
        name="alt_synth",
        rules_factory=DefaultRules,
        rounds=1,
        use_alt_synthesis_prompt=True,
    ),
    FormatVariant(
        name="silent_revise",
        rules_factory=SilentReviseRules,
        rounds=2,
        use_alt_synthesis_prompt=False,
    ),
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
    variant: FormatVariant,
    elders: dict[ElderId, ElderPort],
    store: JsonFileStore,
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
        rules=variant.rules_factory(),
    )
    for _ in range(variant.rounds):
        await svc.run_round(debate)

    synthesis_override = (
        build_alt_synthesis(debate, synthesiser) if variant.use_alt_synthesis_prompt else None
    )
    await svc.synthesize(debate, synthesiser, synthesis_prompt_override=synthesis_override)
    return debate.id


async def run_format_ablation(
    *,
    variants: tuple[FormatVariant, ...],
    roster: RosterSpec,
    prompts: list[CorpusPrompt],
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    elder_factory: ElderFactory,
) -> Path:
    """Run all (variant, prompt) pairs, idempotent at pair granularity."""
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
                variant=variant,
                elders=elders,
                store=store,
                synthesiser=synthesiser,
            )
            manifest["entries"].append(
                {
                    "roster": variant.name,  # re-used as the grouping key for the scorer
                    "prompt_id": prompt.id,
                    "debate_id": debate_id,
                    "synthesiser": synthesiser,
                }
            )
            _write_manifest(manifest_path, manifest)
    return manifest_path
