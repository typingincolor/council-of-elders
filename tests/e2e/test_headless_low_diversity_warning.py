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
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude original.",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "R3 Claude\nCONVERGED: yes",
                "Final synth.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=[
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
                "R3 Gemini\nCONVERGED: yes",
            ],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=[
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
                "R3 ChatGPT\nCONVERGED: yes",
            ],
        ),
    }


def _elders_r1_only():
    return {
        "claude": FakeElder(elder_id="claude", replies=["R1 Claude only."]),
        "gemini": FakeElder(elder_id="gemini", replies=["R1 Gemini only."]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["R1 ChatGPT only."]),
    }


async def test_low_diversity_mode_skips_debate_and_returns_best_r1(capsys):
    judge = FakeElder(
        elder_id="claude",
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
        synthesizer="claude",
        best_r1_judge=judge,
        policy=override,
    )
    out = capsys.readouterr().out
    assert "Low-diversity roster" in out
    assert "R1 Claude only." in out
    assert "Answer (best-R1, Claude)" in out
    # Synthesis did not run, R2 did not run.
    assert "Final synth." not in out
    assert "Round 2" not in out


async def test_homogeneous_roster_auto_picks_best_r1_only(capsys):
    # Three identical model strings → tier-1 heuristic classifies as low.
    roster = RosterSpec(
        name="homogeneous",
        models={
            "claude": "openai/gpt-5-mini",
            "gemini": "openai/gpt-5-mini",
            "chatgpt": "openai/gpt-5-mini",
        },
    )
    judge = FakeElder(
        elder_id="claude",
        replies=["best: 2\nreason: gemini slot clearest.\n"],
    )
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=_elders_r1_only(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="claude",
        best_r1_judge=judge,
        roster_spec=roster,  # no explicit policy — derive from diversity
    )
    out = capsys.readouterr().out
    assert "Low-diversity roster" in out
    assert "unsafe_consensus_risk" not in out  # flag name shouldn't leak verbatim
    assert "Answer (best-R1, Gemini)" in out
    assert "Final synth." not in out


async def test_high_diversity_roster_runs_full_debate(capsys):
    roster = RosterSpec(
        name="mixed",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "meta-llama/llama-3.1-70b-instruct",
            "chatgpt": "openai/gpt-5",
        },
    )
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=_elders_full_debate_ready(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="claude",
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
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "anthropic/claude-haiku-4.5",
            "chatgpt": "openai/gpt-5",
        },
    )
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "Final synth.",  # synthesis call — single_critique still synthesises
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=[
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
            ],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=[
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
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
        synthesizer="claude",
        roster_spec=roster,
    )
    out = capsys.readouterr().out
    assert "Round 1" in out
    assert "Round 2" in out
    assert "Round 3" not in out
    assert "Final synth." in out
