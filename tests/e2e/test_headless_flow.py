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
        "ada": _fake(
            "ada",
            [
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "Final synth.",
            ],
        ),
        "kai": _fake(
            "kai",
            [
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: yes",
            ],
        ),
        "mei": _fake(
            "mei",
            [
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Why?",
                "R3 Mei\nCONVERGED: yes",
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
        synthesizer="ada",
    )
    out = capsys.readouterr().out
    assert "Round 1" in out and "Round 2" in out
    assert "R1 Ada" in out
    assert "R2 Ada" in out
    assert "Final synth." in out


async def test_headless_early_terminates_on_convergence(capsys):
    # All three converge in R3; default max_rounds=3, so exactly 3 rounds run.
    elders = {
        "ada": _fake(
            "ada",
            [
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "Synth.",
            ],
        ),
        "kai": _fake(
            "kai",
            [
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: yes",
            ],
        ),
        "mei": _fake(
            "mei",
            [
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
        max_rounds=6,  # cap high; convergence in R3 stops the loop.
    )
    out = capsys.readouterr().out
    # Ensure R3 was the last round — "Round 4" should not appear.
    assert "Round 3" in out
    assert "Round 4" not in out


async def test_headless_respects_max_rounds(capsys):
    # Elders never converge; max_rounds=4 caps the loop.
    elders = {
        "ada": _fake(
            "ada",
            [
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: no\n\nQUESTIONS:\n@kai Why?",
                "R4 Ada\nCONVERGED: no\n\nQUESTIONS:\n@kai Why?",
                "Synth.",
            ],
        ),
        "kai": _fake(
            "kai",
            [
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: no\n\nQUESTIONS:\n@ada Why?",
                "R4 Kai\nCONVERGED: no\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
        "mei": _fake(
            "mei",
            [
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Why?",
                "R3 Mei\nCONVERGED: no\n\nQUESTIONS:\n@kai Why?",
                "R4 Mei\nCONVERGED: no\n\nQUESTIONS:\n@kai Why?",
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
        max_rounds=4,
    )
    out = capsys.readouterr().out
    assert "Round 4" in out
    assert "Round 5" not in out


async def test_headless_generates_and_saves_debate_report(tmp_path, capsys):
    from council.adapters.storage.report_file import ReportFileStore

    reports_dir = tmp_path / "reports"
    elders = {
        "ada": _fake(
            "ada",
            [
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "The final answer.",
                "Ada took position A, Kai probed on scope, all converged.",
            ],
        ),
        "kai": _fake(
            "kai",
            [
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
        "mei": _fake(
            "mei",
            [
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@ada Why?",
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
        max_rounds=2,
        report_store=ReportFileStore(root=reports_dir),
    )
    out = capsys.readouterr().out
    assert "--- Debate report ---" in out
    assert "Ada took position A" in out

    files = list(reports_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "## Narrative" in content
    assert "Ada took position A" in content


async def test_headless_warns_when_max_rounds_hit_without_convergence(capsys):
    # Elders never converge; --max-rounds=3 stops the loop; a warning is emitted
    # before synthesis runs.
    elders = {
        "ada": _fake(
            "ada",
            [
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: no\n\nQUESTIONS:\n@kai Why?",
                "Synth.",
            ],
        ),
        "kai": _fake(
            "kai",
            [
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: no\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
        "mei": _fake(
            "mei",
            [
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Why?",
                "R3 Mei\nCONVERGED: no\n\nQUESTIONS:\n@kai Why?",
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
        max_rounds=3,
    )
    out = capsys.readouterr().out
    assert "Hit policy max_rounds=3 without full convergence" in out
    assert "best-effort" in out


async def test_headless_does_not_warn_when_convergence_reached(capsys):
    elders = {
        "ada": _fake(
            "ada",
            [
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "Synth.",
            ],
        ),
        "kai": _fake(
            "kai",
            [
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                "R3 Kai\nCONVERGED: yes",
            ],
        ),
        "mei": _fake(
            "mei",
            [
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
        max_rounds=3,
    )
    out = capsys.readouterr().out
    assert "without all elders converging" not in out


async def test_headless_rejects_max_rounds_below_2():
    with pytest.raises(ValueError):
        await run_headless(
            prompt="Q?",
            pack=_pack(),
            elders={},
            store=InMemoryStore(),
            clock=_clock(),
            bus=InMemoryBus(),
            synthesizer="ada",
            max_rounds=1,
        )
