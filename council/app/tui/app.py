from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from typing import Literal

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, RichLog

from council.adapters.bus.in_memory import InMemoryBus
from council.app.tui.cost_notifier import CostNotifier
from council.app.tui.council_view import CouncilView
from council.app.tui.health_check import HealthChecker
from council.app.tui.notices import CouncilNotices
from council.app.tui.report_writer import DebateReportWriter
from council.app.tui.widgets import CouncilInput, SynthesizerModal
from council.domain.debate_service import DebateService
from council.domain.draft_analysis import analyze_drafts
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    UserMessageReceived,
)
from council.domain.models import Debate, ElderId, Turn
from council.domain.ports import (
    Clock,
    CouncilPackLoader,
    ElderPort,
    TranscriptStore,
)


class CouncilApp(App):
    CSS = """
    #notices { height: auto; max-height: 6; padding: 0 1; }
    #view { height: 1fr; }
    #input { dock: bottom; min-height: 3; max-height: 8; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("c", "continue_round", "Continue", show=False),
        Binding("s", "synthesize", "Synthesize", show=False),
        Binding("d", "analyze_drafts", "Compare drafts", show=False),
        Binding("a", "abandon", "Abandon", show=False),
        Binding("o", "override", "Override convergence", show=False),
        Binding("f", "toggle_layout", "Toggle layout", show=False),
        Binding("1", "focus_pane('ada')", "Ada", show=False),
        Binding("2", "focus_pane('kai')", "Kai", show=False),
        Binding("3", "focus_pane('mei')", "Mei", show=False),
        Binding("4", "focus_pane('synthesis')", "Synthesis", show=False),
    ]
    _ELDER_LABELS: dict[ElderId, str] = {"ada": "Ada", "kai": "Kai", "mei": "Mei"}

    def __init__(
        self,
        *,
        elders: dict[ElderId, ElderPort],
        store: TranscriptStore,
        clock: Clock,
        pack_loader: CouncilPackLoader,
        pack_name: str,
        using_openrouter: bool = False,
        report_store=None,  # ReportFileStore | None
        mode: Literal["r1_only", "full"] = "r1_only",
    ) -> None:
        super().__init__()
        self._elders = elders
        self._pack_loader = pack_loader
        self._pack_name = pack_name
        self._using_openrouter = using_openrouter
        # "r1_only" (default): stop after R1, await user decision. The
        # 2026-04 experiments found this shape strongest for diverse
        # rosters and friendlier for drafting (three independent takes).
        # "full" runs R1+R2 back-to-back as the legacy TUI behavior.
        self._mode: Literal["r1_only", "full"] = mode
        self._bus = InMemoryBus()
        self._service = DebateService(elders=elders, store=store, clock=clock, bus=self._bus)
        self._debate: Debate | None = None
        self.awaiting_decision: bool = False
        self.is_finished: bool = False
        # Public buffer observed by e2e tests (via ``app.rendered_lines``).
        # CouncilNotices appends here on every write.
        self.rendered_lines: list[str] = []
        self._tasks: set[asyncio.Task] = set()
        self._view = CouncilView(clock=clock)
        self._notices: CouncilNotices | None = None  # set in on_mount
        self._health_checker = HealthChecker(elders=elders, labels=self._ELDER_LABELS)
        self._cost_notifier = CostNotifier(elders=elders)
        self._report_writer = DebateReportWriter(
            service=self._service, view=self._view, report_store=report_store
        )

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="notices", markup=True, wrap=True, highlight=False)
        yield self._view
        yield CouncilInput(id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self._notices = CouncilNotices(
            log=self.query_one("#notices", RichLog),
            buffer=self.rendered_lines,
        )
        self._stream_task = self._spawn(self._consume_events())
        self._input().focus()
        self._spawn(self._run_health_checks())

    async def on_unmount(self) -> None:
        if hasattr(self, "_stream_task"):
            self._stream_task.cancel()
        for task in list(self._tasks):
            task.cancel()

    async def _consume_events(self) -> None:
        async for ev in self._bus.subscribe():
            if isinstance(ev, TurnStarted):
                self._on_turn_started(ev)
            elif isinstance(ev, TurnCompleted):
                self._on_turn_completed(ev)
            elif isinstance(ev, TurnFailed):
                self._on_turn_failed(ev)
            elif isinstance(ev, RoundCompleted):
                self._on_round_completed(ev)
            elif isinstance(ev, SynthesisCompleted):
                self._on_synthesis_completed(ev)
            elif isinstance(ev, UserMessageReceived):
                self._on_user_message_received(ev)

    def _input(self) -> CouncilInput:
        return self.query_one("#input", CouncilInput)

    def _on_turn_started(self, ev: TurnStarted) -> None:
        self._view.pane(ev.elder).begin_thinking(ev.round_number)

    def _on_turn_completed(self, ev: TurnCompleted) -> None:
        self._view.pane(ev.elder).end_thinking_completed(ev.answer, questions=ev.questions)
        for q in ev.questions:
            self._view.pane(q.to_elder).on_incoming_question(q)

    def _on_turn_failed(self, ev: TurnFailed) -> None:
        self._view.pane(ev.elder).end_thinking_failed(ev.error)

    def _on_round_completed(self, ev: RoundCompleted) -> None:
        assert self._notices is not None
        # r1_only mode: decision point after R1 (no auto-R2).
        # full mode: decision point after R2 (R1+R2 auto-chain).
        decision_at = 1 if self._mode == "r1_only" else 2
        if ev.round.number >= decision_at:
            self._set_awaiting_decision(True)
            if ev.round.number == decision_at:
                self._notices.decision_hint(self._mode)
            # Auto-synth modal when all three elders converge (R3+).
            if ev.round.number >= 3 and self._service.rules.is_converged(ev.round):
                self.run_worker(self._synthesize_worker(), exclusive=True)
        if self._using_openrouter:
            self._spawn(self._cost_notifier.emit(self._notices))

    def _on_synthesis_completed(self, ev: SynthesisCompleted) -> None:
        self._view.pane("synthesis").end_thinking_completed(ev.answer)
        self._view.pane("synthesis").focus()
        self.is_finished = True
        self._set_awaiting_decision(False)
        if ev.answer.elder:
            self._spawn(self._write_report(ev.answer.elder))

    def _on_user_message_received(self, ev: UserMessageReceived) -> None:
        for pane_key in ("ada", "kai", "mei"):
            self._view.pane(pane_key).on_user_message(ev.message)

    def _set_awaiting_decision(self, value: bool) -> None:
        self.awaiting_decision = value
        self._input().disabled = not value

    async def _run_health_checks(self) -> None:
        assert self._notices is not None
        all_unhealthy = await self._health_checker.run(self._notices)
        if all_unhealthy:
            self._input().disabled = True

    async def _write_report(self, by: ElderId) -> None:
        assert self._notices is not None
        if self._debate is None:
            return
        await self._report_writer.write(debate=self._debate, by=by, notices=self._notices)

    @on(CouncilInput.Submitted)
    async def _on_input_submitted(self, event: CouncilInput.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        input_widget = self._input()
        input_widget.clear()
        if self._debate is None:
            # First submission — use as the initial prompt.
            pack = self._pack_loader.load(self._pack_name)
            self._debate = Debate(
                id=str(uuid.uuid4()),
                prompt=text,
                pack=pack,
                rounds=[],
                status="in_progress",
                synthesis=None,
            )
            input_widget.disabled = True
            self._view.focus()
            self._spawn(self._opening_exchange())
        else:
            # Between-round user message.
            if not self.awaiting_decision:
                return
            self._spawn(self._service.add_user_message(self._debate, text))

    async def _opening_exchange(self) -> None:
        if self._debate is None:
            return
        await self._service.run_round(self._debate)  # R1
        if self._debate.status != "in_progress":
            return
        if self._mode == "full":
            await self._service.run_round(self._debate)  # R2

    async def action_continue_round(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self._set_awaiting_decision(False)
        self._spawn(self._service.run_round(self._debate))

    async def action_abandon(self) -> None:
        if self._debate is None:
            return
        self._debate.status = "abandoned"
        self.is_finished = True
        self._set_awaiting_decision(False)
        self.exit()

    async def action_override(self) -> None:
        if not self.awaiting_decision or not self._debate or not self._debate.rounds:
            return
        r = self._debate.rounds[-1]
        r.turns = [Turn(elder=t.elder, answer=replace(t.answer, agreed=True)) for t in r.turns]

    async def action_synthesize(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.run_worker(self._synthesize_worker(), exclusive=True)

    async def action_analyze_drafts(self) -> None:
        if not self.awaiting_decision or self._debate is None or not self._debate.rounds:
            return
        self.run_worker(self._analyze_drafts_worker(), exclusive=False)

    async def _analyze_drafts_worker(self) -> None:
        assert self._notices is not None
        if self._debate is None:
            return
        analyzer_id: ElderId = "ada"
        await self._view.show_analysis_pane()
        self._notices.write(f"[dim]Comparing the three drafts (analyst: {analyzer_id})…[/dim]")
        try:
            markdown = await analyze_drafts(self._debate, analyzer=self._elders[analyzer_id])
        except Exception as ex:
            self._notices.write(f"[yellow]Draft analysis failed: {ex}[/yellow]")
            return
        self._view.pane("analysis").append_analysis(markdown, by=analyzer_id.capitalize())
        self._view.pane("analysis").focus()

    async def _synthesize_worker(self) -> None:
        if self._debate is None:
            return
        choice = await self.push_screen_wait(SynthesizerModal())
        if choice is None:
            return
        self._set_awaiting_decision(False)
        await self._view.show_synthesis_pane()
        self._view.pane("synthesis").begin_thinking(round_number=1)
        self._view.pane("synthesis").focus()
        self._spawn(self._service.synthesize(self._debate, by=choice))

    async def action_toggle_layout(self) -> None:
        self._view.toggle_forced_mode()

    async def action_focus_pane(self, key: str) -> None:
        try:
            self._view.pane(key).focus()
        except KeyError:
            pass


def main() -> None:
    from council.app.tui.cli import main as cli_main

    cli_main()


__all__ = ["CouncilApp", "CouncilInput", "main"]
