import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
from tests.e2e.conftest import pane_lines


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_full_debate_via_tui(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude",  # silent R1
                "R2 Claude\n\nQUESTIONS:\n@gemini Timeline?",  # R2 with peer question
                "Final synthesised answer.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=[
                "R1 Gemini",
                "R2 Gemini\n\nQUESTIONS:\n@claude Reasoning?",
            ],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=[
                "R1 ChatGPT",
                "R2 ChatGPT\n\nQUESTIONS:\n@gemini Growth?",
            ],
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"What should I do?")
        await pilot.press("enter")
        # R1 + R2 auto-chain; awaiting_decision flips True only after R2 completes.
        await _wait_until(pilot, lambda: app.awaiting_decision)
        assert len(app._debate.rounds) == 2

        await pilot.press("s")
        await _wait_until(pilot, lambda: len(app.screen_stack) > 1, timeout_s=2.0)
        await pilot.press("1")  # pick Claude as synthesiser
        await _wait_until(pilot, lambda: app.is_finished)

        assert "R1 Claude" in pane_lines(app, "claude")
        assert "R2 Claude" in pane_lines(app, "claude")
        assert "R1 Gemini" in pane_lines(app, "gemini")
        assert "R1 ChatGPT" in pane_lines(app, "chatgpt")
        assert "Final synthesised answer." in pane_lines(app, "synthesis")


async def test_auto_synth_modal_when_all_converge_in_r3(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude",
                "R2 Claude\n\nQUESTIONS:\n@gemini Why?",
                "R3 Claude\nCONVERGED: yes",
                "Synthesis by Claude.",
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
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"Go")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)  # after R2
        await pilot.press("c")  # trigger R3
        # Modal pops automatically when all three converge in R3.
        await _wait_until(pilot, lambda: len(app.screen_stack) > 1, timeout_s=5.0)
        await pilot.press("1")  # pick Claude
        await _wait_until(pilot, lambda: app.is_finished)
        assert "Synthesis by Claude." in pane_lines(app, "synthesis")
