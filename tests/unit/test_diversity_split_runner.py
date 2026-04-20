import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.domain.models import ElderId
from council.experiments.diversity_split.conditions import CONDITIONS
from council.experiments.diversity_split.runner import run_experiment
from council.experiments.homogenisation.corpus import CorpusPrompt


def _scripted_elders_for_one_debate() -> dict[ElderId, FakeElder]:
    return {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "R3 Claude\nCONVERGED: yes",
                "final synth",  # synthesis
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=[
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
                "R3 Gemini\nCONVERGED: yes",
                "final synth",
            ],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=[
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
                "R3 ChatGPT\nCONVERGED: yes",
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
