from datetime import datetime, timezone

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


def _single_critique_elders():
    return {
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


async def test_medium_diversity_synthesis_carries_risk_note(capsys):
    roster = RosterSpec(
        name="medium",
        models={
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "anthropic/claude-haiku-4.5",
            "mei": "openai/gpt-5",
        },
    )
    await run_headless(
        prompt="Q?",
        pack=_pack(),
        elders=_single_critique_elders(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        roster_spec=roster,
    )
    out = capsys.readouterr().out
    assert "historically rarely outperforms" in out
    assert "medium-diversity" in out


async def test_high_diversity_synthesis_omits_risk_note(capsys):
    roster = RosterSpec(
        name="high",
        models={
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "meta-llama/llama-3.1-70b-instruct",
            "mei": "openai/gpt-5",
        },
    )
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "ANSWER:\nShip.\n\nWHY:\nok.\n\nDISAGREEMENTS:\n(none)\n",
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
    assert "historically rarely outperforms" not in out


async def test_low_diversity_does_not_synthesise_so_no_risk_note(capsys):
    # best_r1_only mode skips synthesis entirely; there's no synthesis to
    # attach a risk note to.
    roster = RosterSpec(
        name="homogeneous",
        models={
            "ada": "openai/gpt-5-mini",
            "kai": "openai/gpt-5-mini",
            "mei": "openai/gpt-5-mini",
        },
    )
    elders = {
        "ada": FakeElder(elder_id="ada", replies=["R1 Ada only."]),
        "kai": FakeElder(elder_id="kai", replies=["R1 Kai only."]),
        "mei": FakeElder(elder_id="mei", replies=["R1 Mei only."]),
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
    # No synthesis → no risk note (the warning is handled by the
    # low-diversity roster warning branch, which is a different message).
    assert "historically rarely outperforms" not in out
