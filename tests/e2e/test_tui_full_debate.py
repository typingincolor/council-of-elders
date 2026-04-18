from datetime import datetime, timezone
import pytest

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.app.tui.app import CouncilApp


async def test_full_debate_via_tui(tmp_path):
    # Pack with only shared context
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude\nCONVERGED: yes",
                "Final synthesized answer.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini", replies=["R1 Gemini\nCONVERGED: yes"]
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt", replies=["R1 ChatGPT\nCONVERGED: yes"]
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"What should I do?")
        await pilot.press("enter")
        # Wait for round to complete; fake elders are instant
        for _ in range(20):
            await pilot.pause()
            if app.awaiting_decision:
                break
        assert app.awaiting_decision is True
        # Press S to synthesize
        await pilot.press("s")
        # Synthesizer modal appears; choose Claude
        await pilot.press("1")  # 1 => Claude
        for _ in range(20):
            await pilot.pause()
            if app.is_finished:
                break
        assert app.is_finished is True

    # Stream should contain all three elder answers and the synthesis
    transcript = "\n".join(app.rendered_lines)
    assert "R1 Claude" in transcript
    assert "R1 Gemini" in transcript
    assert "R1 ChatGPT" in transcript
    assert "Final synthesized answer." in transcript
