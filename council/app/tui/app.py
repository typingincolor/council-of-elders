from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, RichLog, Static, TextArea

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.bootstrap import build_elders
from council.app.config import load_config
from council.app.tui.council_view import CouncilView
from council.domain.debate_service import DebateService
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


class CouncilInput(TextArea):
    """A TextArea where Enter submits and Ctrl+Enter inserts a newline."""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    BINDINGS = [
        # priority=True so our Enter handler runs BEFORE TextArea's built-in
        # enter-inserts-newline binding.
        Binding("enter", "submit", "Submit", show=False, priority=True),
        Binding("ctrl+enter", "newline", "Insert newline", show=False),
    ]

    def action_submit(self) -> None:
        self.post_message(self.Submitted(self.text))

    def action_newline(self) -> None:
        self.insert("\n")


class SynthesizerModal(ModalScreen[ElderId]):
    BINDINGS = [
        Binding("1", "pick('ada')", "Ada"),
        Binding("2", "pick('kai')", "Kai"),
        Binding("3", "pick('mei')", "Mei"),
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Who should synthesize?"),
            Static("[1] Ada   [2] Kai   [3] Mei   [Esc] Cancel"),
        )

    def action_pick(self, elder: str) -> None:
        self.dismiss(elder)  # type: ignore[arg-type]


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
        Binding("a", "abandon", "Abandon", show=False),
        Binding("o", "override", "Override convergence", show=False),
        Binding("f", "toggle_layout", "Toggle layout", show=False),
        Binding("1", "focus_pane('ada')", "Ada", show=False),
        Binding("2", "focus_pane('kai')", "Kai", show=False),
        Binding("3", "focus_pane('mei')", "Mei", show=False),
        Binding("4", "focus_pane('synthesis')", "Synthesis", show=False),
    ]

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
    ) -> None:
        super().__init__()
        self._elders = elders
        self._store = store
        self._clock = clock
        self._pack_loader = pack_loader
        self._pack_name = pack_name
        self._using_openrouter = using_openrouter
        self._prev_cost_total: float = 0.0
        self._bus = InMemoryBus()
        self._service = DebateService(elders=elders, store=store, clock=clock, bus=self._bus)
        self._debate: Debate | None = None
        self.awaiting_decision: bool = False
        self.is_finished: bool = False
        self.rendered_lines: list[str] = []  # test-observable notice buffer
        self._tasks: set[asyncio.Task] = set()
        self._view = CouncilView(clock=clock)
        self._report_store = report_store

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
        self._stream_task = self._spawn(self._consume_events())
        self.query_one("#input", CouncilInput).focus()
        self._spawn(self._run_health_checks())

    async def on_unmount(self) -> None:
        if hasattr(self, "_stream_task"):
            self._stream_task.cancel()
        for task in list(self._tasks):
            task.cancel()

    # --- event fan-out ---------------------------------------------------
    async def _consume_events(self) -> None:
        async for ev in self._bus.subscribe():
            if isinstance(ev, TurnStarted):
                self._view.pane(ev.elder).begin_thinking(ev.round_number)
            elif isinstance(ev, TurnCompleted):
                self._view.pane(ev.elder).end_thinking_completed(ev.answer, questions=ev.questions)
                # Fan each outgoing question into the TARGET elder's pane.
                for q in ev.questions:
                    self._view.pane(q.to_elder).on_incoming_question(q)
            elif isinstance(ev, TurnFailed):
                self._view.pane(ev.elder).end_thinking_failed(ev.error)
            elif isinstance(ev, RoundCompleted):
                # Opening exchange (R1+R2) runs back-to-back; only re-enable
                # input and surface decision state after round 2 completes.
                if ev.round.number >= 2:
                    self.awaiting_decision = True
                    self.query_one("#input", CouncilInput).disabled = False
                    # Auto-synth modal when all three elders converge (R3+).
                    if ev.round.number >= 3 and self._service.rules.is_converged(ev.round):
                        self.run_worker(self._synthesize_worker(), exclusive=True)
                if self._using_openrouter:
                    self._spawn(self._write_cost_notice())
            elif isinstance(ev, SynthesisCompleted):
                self._view.pane("synthesis").end_thinking_completed(ev.answer)
                self._view.pane("synthesis").focus()
                self.is_finished = True
                self.awaiting_decision = False
                # Auto-generate a debate report and write it to disk.
                if ev.answer.elder:
                    self._spawn(self._generate_and_write_report(ev.answer.elder))
            elif isinstance(ev, UserMessageReceived):
                # Dispatch to all three elder panes for inline rendering.
                for pane_key in ("ada", "kai", "mei"):
                    self._view.pane(pane_key).on_user_message(ev.message)

    # --- health check ----------------------------------------------------
    async def _run_health_checks(self) -> None:
        labels: dict[ElderId, str] = {
            "ada": "Ada",
            "kai": "Kai",
            "mei": "Mei",
        }

        async def _probe(elder_id: ElderId) -> tuple[ElderId, bool]:
            try:
                ok = await self._elders[elder_id].health_check()
            except Exception:
                ok = False
            return elder_id, ok

        results = await asyncio.gather(*(_probe(eid) for eid in self._elders))
        unhealthy = [eid for eid, ok in results if not ok]
        if not unhealthy:
            return
        for eid in unhealthy:
            self._write_notice(
                f"[yellow]⚠ {labels[eid]} CLI is unavailable or unauthenticated. "
                f"Install it and run its `login` command before asking a question.[/yellow]"
            )
        if len(unhealthy) == len(self._elders):
            self.query_one("#input", CouncilInput).disabled = True
            self._write_notice(
                "[red]No elders available. Fix the vendor CLI setup above, "
                "then restart the app.[/red]"
            )

    def _write_notice(self, line: str) -> None:
        self.rendered_lines.append(line)
        self.query_one("#notices", RichLog).write(line)

    async def _write_cost_notice(self) -> None:
        from council.adapters.elders.openrouter import (
            OpenRouterAdapter,
            format_cost_notice,
        )

        current = sum(
            e.session_cost_usd for e in self._elders.values() if isinstance(e, OpenRouterAdapter)
        )
        delta = current - self._prev_cost_total
        self._prev_cost_total = current

        any_or = next(
            (e for e in self._elders.values() if isinstance(e, OpenRouterAdapter)),
            None,
        )
        used, limit = (0.0, None)
        if any_or is not None:
            used, limit = await any_or.fetch_credits()

        line = format_cost_notice(
            elders=self._elders,
            round_cost_delta_usd=delta,
            credits_used=used,
            credits_limit=limit,
        )
        self._write_notice(f"[blue]{line}[/blue]")

    # --- user actions ----------------------------------------------------
    @on(CouncilInput.Submitted)
    async def _on_input_submitted(self, event: CouncilInput.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        input_widget = self.query_one("#input", CouncilInput)
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

    async def _generate_and_write_report(self, by: ElderId) -> None:
        """Generate the debate report and render/save it."""
        if self._debate is None:
            return
        try:
            markdown = await self._service.generate_report(self._debate, by=by)
        except Exception as ex:
            self._write_notice(f"[yellow]Report generation failed: {ex}[/yellow]")
            return
        self._view.pane("synthesis").append_report(markdown)
        if self._report_store is not None:
            try:
                path = self._report_store.save(debate_id=self._debate.id, markdown=markdown)
                self._write_notice(f"[blue]Debate report saved to {path}[/blue]")
            except Exception as ex:
                self._write_notice(f"[yellow]Report file write failed: {ex}[/yellow]")

    async def _opening_exchange(self) -> None:
        """Run R1 (silent initial) then R2 (cross-exam) back-to-back.

        Between R1 and R2, the RoundCompleted handler keeps the input
        disabled and awaiting_decision=False (that check is gated on
        round.number >= 2). After R2 completes the user can interact.
        """
        if self._debate is None:
            return
        await self._service.run_round(self._debate)  # R1
        if self._debate.status != "in_progress":
            return
        await self._service.run_round(self._debate)  # R2

    async def action_continue_round(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.awaiting_decision = False
        self.query_one("#input", CouncilInput).disabled = True
        self._spawn(self._service.run_round(self._debate))

    async def action_abandon(self) -> None:
        if self._debate is None:
            return
        self._debate.status = "abandoned"
        self.is_finished = True
        self.awaiting_decision = False
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

    async def _synthesize_worker(self) -> None:
        if self._debate is None:
            return
        choice = await self.push_screen_wait(SynthesizerModal())
        if choice is None:
            return
        self.awaiting_decision = False
        # Disable the input so keystrokes don't get swallowed by the TextArea
        # while the user is waiting for synthesis.
        self.query_one("#input", CouncilInput).disabled = True
        # Reveal the synthesis pane in columns mode (no-op in tabs mode) and
        # focus it so the ticker is immediately visible to the user.
        self._view.show_synthesis_pane()
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
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="council")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
    parser.add_argument("--reports-root", default=str(Path.home() / ".council" / "reports"))
    parser.add_argument(
        "--claude-model",
        default=os.environ.get("COUNCIL_CLAUDE_MODEL"),
        help="Model alias or full name passed to `claude --model` (e.g. sonnet, opus).",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("COUNCIL_GEMINI_MODEL"),
        help="Model name passed to `gemini -m` (e.g. gemini-2.5-flash — recommended; Pro has tight quota).",
    )
    parser.add_argument(
        "--codex-model",
        default=os.environ.get("COUNCIL_CODEX_MODEL"),
        help="Model name passed to `codex exec -m` (e.g. gpt-5-codex).",
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    (packs_root / args.pack).mkdir(exist_ok=True)  # ensure bare pack works

    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "ada": args.claude_model,
        "kai": args.gemini_model,
        "mei": args.codex_model,
    }
    elders, using_openrouter, _roster_spec = build_elders(config, cli_models=cli_models)

    from council.adapters.storage.report_file import ReportFileStore

    app = CouncilApp(
        elders=elders,
        store=JsonFileStore(root=Path(args.store_root)),
        clock=SystemClock(),
        pack_loader=FilesystemPackLoader(root=packs_root),
        pack_name=args.pack,
        using_openrouter=using_openrouter,
        report_store=ReportFileStore(root=Path(args.reports_root)),
    )
    app.run()
