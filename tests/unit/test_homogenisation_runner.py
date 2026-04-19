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
                r1.format(slot=slot),
                r2,
                r3,
                synth,
                "Report body.",
                "Narrative audit body.",
            ],
        )

    return {slot: make(slot) for slot in ("claude", "gemini", "chatgpt")}


@pytest.mark.asyncio
async def test_run_probe_produces_manifest_with_every_pair(tmp_path: Path) -> None:
    prompts = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    specs = (
        RosterSpec(name="r1", models={"claude": "a/a", "gemini": "a/a", "chatgpt": "a/a"}),
        RosterSpec(name="r2", models={"claude": "b/b", "gemini": "b/b", "chatgpt": "b/b"}),
    )

    def elder_factory(_spec: RosterSpec) -> dict[ElderId, Any]:
        return _mk_elders()

    run_id = "2026-04-19-test"
    manifest_path = await run_probe(
        rosters=specs,
        prompts=prompts,
        run_id=run_id,
        runs_root=tmp_path,
        debate_store_root=tmp_path / "debates",
        elder_factory=elder_factory,
        max_rounds=3,
    )
    manifest = json.loads(Path(manifest_path).read_text())
    assert len(manifest["entries"]) == 2  # 2 rosters × 1 prompt
    rosters_seen = {e["roster"] for e in manifest["entries"]}
    assert rosters_seen == {"r1", "r2"}
    assert all("debate_id" in e for e in manifest["entries"])
    assert all(e["synthesiser"] in {"claude", "gemini", "chatgpt"} for e in manifest["entries"])


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
        rosters=specs,
        prompts=prompts,
        run_id=run_id,
        runs_root=tmp_path,
        debate_store_root=tmp_path / "debates",
        elder_factory=elder_factory,
        max_rounds=3,
    )
    await run_probe(  # second call, should skip
        rosters=specs,
        prompts=prompts,
        run_id=run_id,
        runs_root=tmp_path,
        debate_store_root=tmp_path / "debates",
        elder_factory=elder_factory,
        max_rounds=3,
    )
    assert calls["n"] == 1  # second call skipped entirely
