from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.models import CouncilPack


def _pack():
    return CouncilPack(name="bare", shared_context=None, personas={})


def _clock():
    return FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc))


def _elders():
    return {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
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


async def test_best_r1_printed_when_judge_available(capsys):
    judge = FakeElder(
        elder_id="ada",
        replies=["best: 2\nreason: Kai cut the clearest line.\n"],
    )
    store = InMemoryStore()
    await run_headless(
        prompt="What should I do?",
        pack=_pack(),
        elders=_elders(),
        store=store,
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        best_r1_judge=judge,
    )
    out = capsys.readouterr().out
    assert "Best R1 (judge-picked): Kai" in out
    assert "Kai cut the clearest line" in out
    # debate was saved with best_r1_elder recorded
    debates = list(store._data.values())
    assert len(debates) == 1
    assert debates[0].best_r1_elder == "kai"


async def test_baseline_unavailable_message_when_no_judge(capsys):
    await run_headless(
        prompt="What should I do?",
        pack=_pack(),
        elders=_elders(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
    )
    out = capsys.readouterr().out
    assert "Best-R1 baseline unavailable" in out


async def test_best_r1_does_not_block_synthesis(capsys):
    judge = FakeElder(
        elder_id="ada",
        replies=["best: 1\nreason: first one was tightest.\n"],
    )
    await run_headless(
        prompt="What?",
        pack=_pack(),
        elders=_elders(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="ada",
        best_r1_judge=judge,
    )
    out = capsys.readouterr().out
    assert "Best R1 (judge-picked): Ada" in out
    assert "Final synth." in out  # synthesis still emitted
