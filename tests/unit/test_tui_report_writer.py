from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from council.app.tui.notices import CouncilNotices
from council.app.tui.report_writer import DebateReportWriter
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)


class _StubLog:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, line: str) -> None:
        self.written.append(line)


def _notices():
    buf: list[str] = []
    return CouncilNotices(log=_StubLog(), buffer=buf), buf


def _debate():
    return Debate(
        id="debate-42",
        prompt="q",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[
            Round(
                number=1,
                turns=[
                    Turn(
                        elder="ada",
                        answer=ElderAnswer(
                            elder="ada",
                            text="hi",
                            error=None,
                            agreed=None,
                            created_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
                        ),
                    )
                ],
            )
        ],
        status="in_progress",
        synthesis=None,
    )


def _view_with_append_report():
    """Build a view whose synthesis pane captures append_report calls."""
    view = MagicMock()
    pane = MagicMock()
    view.pane.return_value = pane
    return view, pane


class TestDebateReportWriter:
    async def test_success_path_renders_and_saves(self):
        service = MagicMock()
        service.generate_report = AsyncMock(return_value="# report")
        view, pane = _view_with_append_report()
        store = MagicMock()
        store.save.return_value = Path("/tmp/rep.md")
        notices, buf = _notices()
        writer = DebateReportWriter(service=service, view=view, report_store=store)

        await writer.write(debate=_debate(), by="ada", notices=notices)

        service.generate_report.assert_awaited_once()
        view.pane.assert_called_with("synthesis")
        pane.append_report.assert_called_once_with("# report")
        store.save.assert_called_once_with(debate_id="debate-42", markdown="# report")
        assert any("Debate report saved to /tmp/rep.md" in line for line in buf)

    async def test_no_store_renders_but_does_not_save(self):
        service = MagicMock()
        service.generate_report = AsyncMock(return_value="# report")
        view, pane = _view_with_append_report()
        notices, buf = _notices()
        writer = DebateReportWriter(service=service, view=view, report_store=None)

        await writer.write(debate=_debate(), by="ada", notices=notices)

        pane.append_report.assert_called_once_with("# report")
        assert buf == []  # No saved-path notice when there is no store.

    async def test_generate_failure_writes_yellow_notice_and_skips_render(self):
        service = MagicMock()
        service.generate_report = AsyncMock(side_effect=RuntimeError("judge offline"))
        view, pane = _view_with_append_report()
        notices, buf = _notices()
        writer = DebateReportWriter(service=service, view=view, report_store=MagicMock())

        await writer.write(debate=_debate(), by="ada", notices=notices)

        pane.append_report.assert_not_called()
        assert any("Report generation failed: judge offline" in line for line in buf)

    async def test_save_failure_writes_yellow_notice_after_rendering(self):
        service = MagicMock()
        service.generate_report = AsyncMock(return_value="# report")
        view, pane = _view_with_append_report()
        store = MagicMock()
        store.save.side_effect = OSError("disk full")
        notices, buf = _notices()
        writer = DebateReportWriter(service=service, view=view, report_store=store)

        await writer.write(debate=_debate(), by="ada", notices=notices)

        # Render happens before save — assert that.
        pane.append_report.assert_called_once_with("# report")
        assert any("Report file write failed: disk full" in line for line in buf)
