import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.adapters.storage.report_file import ReportFileStore
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


async def test_debate_report_appended_to_synthesis_pane_and_written_to_file(tmp_path):
    (tmp_path / "bare").mkdir()
    reports_dir = tmp_path / "reports"

    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                "The synthesised answer.",
                "Ada argued for option A initially. Kai conceded on scope. "
                "All three converged by R3.",
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "R1 Kai",
                "R2 Kai\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "R1 Mei",
                "R2 Mei\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
    }

    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
        report_store=ReportFileStore(root=reports_dir),
    )

    async with app.run_test() as pilot:
        await pilot.press(*"Go")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)  # after R2
        await pilot.press("s")
        await _wait_until(pilot, lambda: len(app.screen_stack) > 1, timeout_s=2.0)
        await pilot.press("1")  # pick Ada as synthesiser
        await _wait_until(pilot, lambda: app.is_finished)
        # Wait for the report worker to finish.
        await _wait_until(
            pilot,
            lambda: "Debate report saved" in "\n".join(app.rendered_lines),
            timeout_s=3.0,
        )

    synth_text = pane_lines(app, "synthesis")
    assert "The synthesised answer." in synth_text
    assert "--- Debate report ---" in synth_text
    assert "Debate metadata" in synth_text
    assert "Ada argued for option A initially" in synth_text

    # File was written.
    files = list(reports_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Synthesised answer" in content
    assert "The synthesised answer." in content
    assert "## Narrative" in content
    assert "Ada argued for option A initially" in content
