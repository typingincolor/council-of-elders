"""Pressing `d` after R1 produces a draft-comparison analysis in the
synthesis pane (agreements/divergences/unique points).

Uses one of the elders as the analyzer so the TUI needs no new wiring.
"""

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
        if elapsed >= timeout_s:
            raise AssertionError("condition never became true")
        await pilot.pause(tick)
        elapsed += tick


async def test_pressing_d_after_r1_surfaces_draft_analysis(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    # Ada is the analyzer by default; her second reply is the analysis
    # response (after her R1 draft reply).
    analysis_md = (
        "## Agreements\n"
        "- All three propose an agenda.\n\n"
        "## Divergences\n"
        "- Ada commits to Oct 24; Kai and Mei leave the date as a placeholder.\n\n"
        "## Unique to each\n"
        "- Ada: concrete timing.\n"
        "- Kai: performance-review framing.\n"
        "- Mei: neutral structure.\n\n"
        "## Reading recommendation\n"
        "If you want a sendable draft, start from Ada.\n"
    )
    elders = {
        "ada": FakeElder(elder_id="ada", replies=["R1 Ada.", analysis_md]),
        "kai": FakeElder(elder_id="kai", replies=["R1 Kai."]),
        "mei": FakeElder(elder_id="mei", replies=["R1 Mei."]),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 21, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"Draft an email about X")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)
        # Decision hint now advertises [d].
        assert any("compare drafts" in line for line in app.rendered_lines)

        await pilot.press("d")
        # Wait for the analysis to land in the synthesis pane.
        await _wait_until(pilot, lambda: "Draft analysis" in pane_lines(app, "synthesis"))
        text = pane_lines(app, "synthesis")
        assert "Draft analysis by Ada" in text
        assert "Agreements" in text
        assert "Divergences" in text
        assert "Ada commits to Oct 24" in text
