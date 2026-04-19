from datetime import datetime, timezone

import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.models import CouncilPack


def _pack():
    return CouncilPack(name="bare", shared_context=None, personas={})


def _fake(elder, replies):
    return FakeElder(elder_id=elder, replies=replies)


def _clock():
    return FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc))


async def test_headless_runs_r1_r2_then_synthesises_by_default(capsys):
    # max_rounds=3 default. R1+R2 mandatory. R3 optional (but elders don't
    # need to converge here — they just need enough replies for R1+R2 +
    # possibly R3 + synth).
    elders = {
        "claude": _fake(
            "claude",
            [
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "R3 Claude\nCONVERGED: yes",
                "Final synth.",
            ],
        ),
        "gemini": _fake(
            "gemini",
            [
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
                "R3 Gemini\nCONVERGED: yes",
            ],
        ),
        "chatgpt": _fake(
            "chatgpt",
            [
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
                "R3 ChatGPT\nCONVERGED: yes",
            ],
        ),
    }
    await run_headless(
        prompt="What should I do?",
        pack=_pack(),
        elders=elders,
        store=InMemoryStore(),
        clock=_clock(),
        bus=InMemoryBus(),
        synthesizer="claude",
    )
    out = capsys.readouterr().out
    assert "Round 1" in out and "Round 2" in out
    assert "R1 Claude" in out
    assert "R2 Claude" in out
    assert "Final synth." in out


async def test_headless_early_terminates_on_convergence(capsys):
    # All three converge in R3; default max_rounds=3, so exactly 3 rounds run.
    elders = {
        "claude": _fake(
            "claude",
            [
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "R3 Claude\nCONVERGED: yes",
                "Synth.",
            ],
        ),
        "gemini": _fake(
            "gemini",
            [
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
                "R3 Gemini\nCONVERGED: yes",
            ],
        ),
        "chatgpt": _fake(
            "chatgpt",
            [
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
                "R3 ChatGPT\nCONVERGED: yes",
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
        max_rounds=6,  # cap high; convergence in R3 stops the loop.
    )
    out = capsys.readouterr().out
    # Ensure R3 was the last round — "Round 4" should not appear.
    assert "Round 3" in out
    assert "Round 4" not in out


async def test_headless_respects_max_rounds(capsys):
    # Elders never converge; max_rounds=4 caps the loop.
    elders = {
        "claude": _fake(
            "claude",
            [
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "R3 Claude\nCONVERGED: no\n\nQUESTIONS:\n@gemini Why?",
                "R4 Claude\nCONVERGED: no\n\nQUESTIONS:\n@gemini Why?",
                "Synth.",
            ],
        ),
        "gemini": _fake(
            "gemini",
            [
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
                "R3 Gemini\nCONVERGED: no\n\nQUESTIONS:\n@claude Why?",
                "R4 Gemini\nCONVERGED: no\n\nQUESTIONS:\n@claude Why?",
            ],
        ),
        "chatgpt": _fake(
            "chatgpt",
            [
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Why?",
                "R3 ChatGPT\nCONVERGED: no\n\nQUESTIONS:\n@gemini Why?",
                "R4 ChatGPT\nCONVERGED: no\n\nQUESTIONS:\n@gemini Why?",
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
        max_rounds=4,
    )
    out = capsys.readouterr().out
    assert "Round 4" in out
    assert "Round 5" not in out


async def test_headless_generates_and_saves_debate_report(tmp_path, capsys):
    from council.adapters.storage.report_file import ReportFileStore

    reports_dir = tmp_path / "reports"
    elders = {
        "claude": _fake(
            "claude",
            [
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "The final answer.",
                "Claude took position A, Gemini probed on scope, all converged.",
            ],
        ),
        "gemini": _fake(
            "gemini",
            [
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Why?",
            ],
        ),
        "chatgpt": _fake(
            "chatgpt",
            [
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@claude Why?",
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
        max_rounds=2,
        report_store=ReportFileStore(root=reports_dir),
    )
    out = capsys.readouterr().out
    assert "--- Debate report ---" in out
    assert "Claude took position A" in out

    files = list(reports_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "## Narrative" in content
    assert "Claude took position A" in content


async def test_headless_rejects_max_rounds_below_2():
    with pytest.raises(ValueError):
        await run_headless(
            prompt="Q?",
            pack=_pack(),
            elders={},
            store=InMemoryStore(),
            clock=_clock(),
            bus=InMemoryBus(),
            synthesizer="claude",
            max_rounds=1,
        )
