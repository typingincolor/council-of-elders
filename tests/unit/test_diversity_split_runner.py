import json
from pathlib import Path

import pytest

from council.adapters.elders.fake import FakeElder
from council.domain.models import ElderId
from council.experiments.diversity_split.conditions import CONDITIONS
from council.experiments.diversity_split.runner import run_experiment
from council.experiments.homogenisation.corpus import CorpusPrompt


def _scripted_elders_for_one_debate() -> dict[ElderId, FakeElder]:
    return {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "final synth",  # synthesis
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: yes",
                "final synth",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Why?",
                "R3 Mei\nCONVERGED: yes",
                "final synth",
            ],
        ),
    }


class TestRunExperiment:
    async def test_manifest_contains_one_entry_per_condition_prompt_pair(self, tmp_path: Path):
        # Single prompt + 4 conditions → 4 entries.
        prompts = [CorpusPrompt(id="p1", shape="strategy", prompt="Q?")]

        def factory(_condition) -> dict[ElderId, FakeElder]:
            return _scripted_elders_for_one_debate()

        manifest_path = await run_experiment(
            conditions=CONDITIONS,
            prompts=prompts,
            run_id="test",
            runs_root=tmp_path / "runs",
            debate_store_root=tmp_path / "debates",
            elder_factory=factory,  # type: ignore[arg-type]
            max_rounds=3,
        )
        manifest = json.loads(manifest_path.read_text())
        assert len(manifest["entries"]) == 4
        condition_names = {e["roster"] for e in manifest["entries"]}
        assert condition_names == {c.name for c in CONDITIONS}

    async def test_is_resumable_from_partial_manifest(self, tmp_path: Path):
        prompts = [CorpusPrompt(id="p1", shape="strategy", prompt="Q?")]

        def factory(_condition) -> dict[ElderId, FakeElder]:
            return _scripted_elders_for_one_debate()

        # First run.
        await run_experiment(
            conditions=CONDITIONS,
            prompts=prompts,
            run_id="test",
            runs_root=tmp_path / "runs",
            debate_store_root=tmp_path / "debates",
            elder_factory=factory,  # type: ignore[arg-type]
            max_rounds=3,
        )
        # Second run with same id — factory should not be called again;
        # supply an exploding factory so any call would fail.

        def exploding(_condition):
            raise AssertionError("factory called for already-complete condition")

        await run_experiment(
            conditions=CONDITIONS,
            prompts=prompts,
            run_id="test",
            runs_root=tmp_path / "runs",
            debate_store_root=tmp_path / "debates",
            elder_factory=exploding,  # type: ignore[arg-type]
            max_rounds=3,
        )
        manifest = json.loads(
            (tmp_path / "runs" / "test" / "manifest.json").read_text()
        )
        assert len(manifest["entries"]) == 4  # unchanged

    async def test_rejects_insufficient_max_rounds(self, tmp_path: Path):
        prompts = [CorpusPrompt(id="p1", shape="strategy", prompt="Q?")]

        def factory(_condition):
            return _scripted_elders_for_one_debate()

        with pytest.raises(ValueError, match="max_rounds"):
            await run_experiment(
                conditions=CONDITIONS,
                prompts=prompts,
                run_id="test",
                runs_root=tmp_path / "runs",
                debate_store_root=tmp_path / "debates",
                elder_factory=factory,  # type: ignore[arg-type]
                max_rounds=1,
            )
