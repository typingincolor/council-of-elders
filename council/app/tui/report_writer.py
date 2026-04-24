from __future__ import annotations

from council.app.tui.council_view import CouncilView
from council.app.tui.notices import CouncilNotices
from council.domain.debate_service import DebateService
from council.domain.models import Debate, ElderId


class DebateReportWriter:
    """Generate the debate report, render it in the synthesis pane, save to disk."""

    def __init__(
        self,
        *,
        service: DebateService,
        view: CouncilView,
        report_store,  # ReportFileStore | None
    ) -> None:
        self._service = service
        self._view = view
        self._report_store = report_store

    async def write(
        self,
        *,
        debate: Debate,
        by: ElderId,
        notices: CouncilNotices,
    ) -> None:
        try:
            markdown = await self._service.generate_report(debate, by=by)
        except Exception as ex:
            notices.write(f"[yellow]Report generation failed: {ex}[/yellow]")
            return
        self._view.pane("synthesis").append_report(markdown)
        if self._report_store is None:
            return
        try:
            path = self._report_store.save(debate_id=debate.id, markdown=markdown)
            notices.write(f"[blue]Debate report saved to {path}[/blue]")
        except Exception as ex:
            notices.write(f"[yellow]Report file write failed: {ex}[/yellow]")
