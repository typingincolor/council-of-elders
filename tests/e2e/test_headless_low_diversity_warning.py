from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.debate_policy import DebatePolicy
from council.domain.models import CouncilPack
from council.domain.roster import RosterSpec


def _pack():
    return CouncilPack(name="bare", shared_context=None, personas={})


def _clock():
    return FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc))


def _elders_full_debate_ready():
    return {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada original.",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "Final synth.",
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: yes",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Why?",
                "R3 Mei\nCONVERGED: yes",
            ],
        ),
    }


def _elders_r1_only():
    return {
        "ada": FakeElder(elder_id="ada", replies=["R1 Ada only."]),
        "kai": FakeElder(elder_id="kai", replies=["R1 Kai only."]),
        "mei": FakeElder(elder_id="mei", replies=["R1 Mei only."]),
    }


async def test_low_diversity_mode_skips_debate_and_returns_best_r1(capsys):
    judge = FakeElder(
        elder_id="ada",
        replies=["best: 1\nreason: first one was tightest.\n"],
    )
    override = DebatePolicy(
        mode="best_r1_only",
        max_rounds=1,
        synthesise=False,
        always_compute_best_r1=True,
        warning="Low-diversity roster — forced mode for test.",
    )
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=_elders_r1_only(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        best_r1_judge=judge,
        policy=override,
    )
    out = capsys.readouterr().out
    assert "Low-diversity roster" in out
    assert "R1 Ada only." in out
    assert "Answer (best-R1, Ada)" in out
    # Synthesis did not run, R2 did not run.
    assert "Final synth." not in out
    assert "Round 2" not in out


async def test_homogeneous_roster_auto_picks_best_r1_only(capsys):
    # Three identical model strings → tier-1 heuristic classifies as low.
    roster = RosterSpec(
        name="homogeneous",
        models={
            "ada": "openai/gpt-5-mini",
            "kai": "openai/gpt-5-mini",
            "mei": "openai/gpt-5-mini",
        },
    )
    judge = FakeElder(
        elder_id="ada",
        replies=["best: 2\nreason: gemini slot clearest.\n"],
    )
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=_elders_r1_only(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        best_r1_judge=judge,
        roster_spec=roster,  # no explicit policy — derive from diversity
    )
    out = capsys.readouterr().out
    assert "Low-diversity roster" in out
    assert "unsafe_consensus_risk" not in out  # flag name shouldn't leak verbatim
    assert "Answer (best-R1, Kai)" in out
    assert "Final synth." not in out


async def test_high_diversity_roster_runs_full_debate(capsys):
    roster = RosterSpec(
        name="mixed",
        models={
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "meta-llama/llama-3.1-70b-instruct",
            "mei": "openai/gpt-5",
        },
    )
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=_elders_full_debate_ready(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        roster_spec=roster,
    )
    out = capsys.readouterr().out
    assert "Low-diversity roster" not in out
    assert "Final synth." in out
    assert "Round 2" in out


async def test_medium_diversity_roster_runs_single_critique(capsys):
    roster = RosterSpec(
        name="two_provider",
        models={
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "anthropic/claude-haiku-4.5",
            "mei": "openai/gpt-5",
        },
    )
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "Final synth.",  # synthesis call — single_critique still synthesises
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Why?",
            ],
        ),
    }
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=elders,
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        roster_spec=roster,
    )
    out = capsys.readouterr().out
    assert "Round 1" in out
    assert "Round 2" in out
    assert "Round 3" not in out
    assert "Final synth." in out
