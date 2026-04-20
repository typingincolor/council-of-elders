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
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude",
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


async def test_best_r1_printed_when_judge_available(capsys):
    judge = FakeElder(
        elder_id="claude",
        replies=["best: 2\nreason: Gemini cut the clearest line.\n"],
    )
    store = InMemoryStore()
    await run_headless(
        prompt="What should I do?",
        pack=_pack(),
        elders=_elders(),
        store=store,
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="claude",
        best_r1_judge=judge,
    )
    out = capsys.readouterr().out
    assert "Best R1 (judge-picked): Gemini" in out
    assert "Gemini cut the clearest line" in out
    # debate was saved with best_r1_elder recorded
    debates = list(store._data.values())
    assert len(debates) == 1
    assert debates[0].best_r1_elder == "gemini"


async def test_baseline_unavailable_message_when_no_judge(capsys):
    await run_headless(
        prompt="What should I do?",
        pack=_pack(),
        elders=_elders(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="claude",
    )
    out = capsys.readouterr().out
    assert "Best-R1 baseline unavailable" in out


async def test_best_r1_does_not_block_synthesis(capsys):
    judge = FakeElder(
        elder_id="claude",
        replies=["best: 1\nreason: first one was tightest.\n"],
    )
    await run_headless(
        prompt="What?",
        pack=_pack(),
        elders=_elders(),
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="claude",
        best_r1_judge=judge,
    )
    out = capsys.readouterr().out
    assert "Best R1 (judge-picked): Claude" in out
    assert "Final synth." in out  # synthesis still emitted
