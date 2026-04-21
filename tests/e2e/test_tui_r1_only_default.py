"""The TUI defaults to ``mode="r1_only"``: run R1, then hand control back
to the user so they can read three drafts, choose to synthesise (`s`),
continue to a cross-examination round (`c`), or finish (`a`).

This is the drafting-friendly default endorsed by the 2026-04 experiments
(R1-only beats full debate on synthesis preference for diverse rosters).
"""

from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        if elapsed >= timeout_s:
            raise AssertionError("condition never became true")
        await pilot.pause(tick)
        elapsed += tick


async def test_default_mode_runs_r1_then_stops(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)
    elders = {
        "ada": FakeElder(elder_id="ada", replies=["R1 Ada draft."]),
        "kai": FakeElder(elder_id="kai", replies=["R1 Kai draft."]),
        "mei": FakeElder(elder_id="mei", replies=["R1 Mei draft."]),
    }
    # mode is not passed — default should be r1_only.
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"Draft an email about X")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)
        # Exactly one round ran — no auto-R2.
        assert len(app._debate.rounds) == 1
        # Decision hint surfaced once to explain the keybindings.
        assert any("R1 complete" in line for line in app.rendered_lines)
        assert any("synthesise" in line for line in app.rendered_lines)


async def test_user_can_continue_to_r2_from_r1_only_default(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=["R1 Ada", "R2 Ada\n\nQUESTIONS:\n@kai Why?"],
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
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"Q?")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)
        assert len(app._debate.rounds) == 1

        # Press `c` to opt into a cross-examination round.
        await pilot.press("c")
        await _wait_until(pilot, lambda: app.awaiting_decision and len(app._debate.rounds) == 2)
        assert len(app._debate.rounds) == 2
