import json
from datetime import datetime, timezone
from pathlib import Path

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.models import CouncilPack
from council.domain.roster import RosterSpec


def _pack():
    return CouncilPack(name="bare", shared_context=None, personas={})


def _clock():
    return FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc))


async def test_summary_written_after_synthesis(tmp_path: Path, capsys):
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "ANSWER:\nShip.\n\nWHY:\nok.\n\nDISAGREEMENTS:\n(none)\n",
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=["R1 Kai", "R2 Kai\n\nQUESTIONS:\n@ada Why?"],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=["R1 Mei", "R2 Mei\n\nQUESTIONS:\n@kai Why?"],
        ),
    }
    best_r1_judge = FakeElder(
        elder_id="ada", replies=["best: 2\nreason: clearer.\n"],
    )
    preference_judge = FakeElder(
        elder_id="ada", replies=["winner: X\nreason: synth wins.\n"],
    )
    roster = RosterSpec(
        name="medium",
        models={
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "anthropic/claude-haiku-4.5",
            "mei": "openai/gpt-5",
        },
    )
    summaries_root = tmp_path / "summaries"

    await run_headless(
        prompt="What should I do?",
        pack=_pack(),
        elders=elders,
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        best_r1_judge=best_r1_judge,
        preference_judge=preference_judge,
        roster_spec=roster,
        run_summary_root=summaries_root,
    )

    # Exactly one summary file written.
    files = list(summaries_root.glob("*-summary.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())

    assert data["prompt"] == "What should I do?"
    assert data["roster"]["name"] == "medium"
    assert data["diversity"]["classification"] == "medium"
    assert data["policy"]["mode"] == "single_critique"
    assert data["rounds_executed"] == 2  # R1 + R2 under single_critique
    assert data["best_r1_elder"] == "kai"
    assert data["synthesis_generated"] is True
    assert data["synthesis_structured"]["answer"] == "Ship."
    assert data["preference"]["winner"] in ("synthesis", "best_r1", "tie")


async def test_summary_includes_warning_for_low_diversity(tmp_path: Path, capsys):
    elders = {
        "ada": FakeElder(elder_id="ada", replies=["R1 Ada."]),
        "kai": FakeElder(elder_id="kai", replies=["R1 Kai."]),
        "mei": FakeElder(elder_id="mei", replies=["R1 Mei."]),
    }
    best_r1_judge = FakeElder(
        elder_id="ada", replies=["best: 1\nreason: tightest.\n"],
    )
    roster = RosterSpec(
        name="homogeneous",
        models={
            "ada": "openai/gpt-5-mini",
            "kai": "openai/gpt-5-mini",
            "mei": "openai/gpt-5-mini",
        },
    )
    summaries_root = tmp_path / "summaries"

    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=elders,
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        best_r1_judge=best_r1_judge,
        roster_spec=roster,
        run_summary_root=summaries_root,
    )

    [summary_path] = list(summaries_root.glob("*-summary.json"))
    data = json.loads(summary_path.read_text())
    assert data["diversity"]["classification"] == "low"
    assert "unsafe_consensus_risk" in data["diversity"]["flags"]
    assert data["policy"]["mode"] == "best_r1_only"
    assert data["policy"]["warning"] is not None
    assert data["synthesis_generated"] is False
    assert data["synthesis_structured"] is None
    # No preference — no synthesis to compare.
    assert data["preference"] is None
    assert data["rounds_executed"] == 1
