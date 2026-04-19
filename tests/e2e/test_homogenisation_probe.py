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
        elder_factory=_elder_factory, max_rounds=3,
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
