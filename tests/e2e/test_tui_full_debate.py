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
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",  # silent R1
                "R2 Ada\n\nQUESTIONS:\n@kai Timeline?",  # R2 with peer question
                "Final synthesised answer.",
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Reasoning?",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@kai Growth?",
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
        await pilot.press("1")  # pick Ada as synthesiser
        await _wait_until(pilot, lambda: app.is_finished)

        assert "R1 Ada" in pane_lines(app, "ada")
        assert "R2 Ada" in pane_lines(app, "ada")
        assert "R1 Kai" in pane_lines(app, "kai")
        assert "R1 Mei" in pane_lines(app, "mei")
        assert "Final synthesised answer." in pane_lines(app, "synthesis")


async def test_auto_synth_modal_when_all_converge_in_r3(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "R3 Ada\nCONVERGED: yes",
                "Synthesis by Ada.",
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
        await pilot.press("1")  # pick Ada
        await _wait_until(pilot, lambda: app.is_finished)
        assert "Synthesis by Ada." in pane_lines(app, "synthesis")
