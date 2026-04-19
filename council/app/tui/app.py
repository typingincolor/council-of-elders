from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.tui.stream import ChronologicalStream, format_event
from council.domain.debate_service import DebateService
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
)
from council.domain.models import (
    Debate,
    ElderId,
    Turn,
)
from council.domain.ports import (
    Clock,
    CouncilPackLoader,
    ElderPort,
    TranscriptStore,
)


class SynthesizerModal(ModalScreen[ElderId]):
    BINDINGS = [
        Binding("1", "pick('claude')", "Claude"),
        Binding("2", "pick('gemini')", "Gemini"),
        Binding("3", "pick('chatgpt')", "ChatGPT"),
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Who should synthesize?"),
            Static("[1] Claude   [2] Gemini   [3] ChatGPT   [Esc] Cancel"),
        )

    def action_pick(self, elder: str) -> None:
        self.dismiss(elder)  # type: ignore[arg-type]


class CouncilApp(App):
    CSS = """
    #stream { height: 1fr; }
    #input { dock: bottom; }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("c", "continue_round", "Continue", show=False),
        Binding("s", "synthesize", "Synthesize", show=False),
        Binding("a", "abandon", "Abandon", show=False),
        Binding("o", "override", "Override convergence", show=False),
    ]

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def __init__(
        self,
        *,
        elders: dict[ElderId, ElderPort],
        store: TranscriptStore,
        clock: Clock,
        pack_loader: CouncilPackLoader,
        pack_name: str,
    ) -> None:
        super().__init__()
        self._elders = elders
        self._store = store
        self._clock = clock
        self._pack_loader = pack_loader
        self._pack_name = pack_name
        self._bus = InMemoryBus()
        self._service = DebateService(elders=elders, store=store, clock=clock, bus=self._bus)
        self._debate: Debate | None = None
        self.awaiting_decision: bool = False
        self.is_finished: bool = False
        self.rendered_lines: list[str] = []
        self._tasks: set[asyncio.Task] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChronologicalStream(id="stream")
        yield Input(placeholder="Ask the council…", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self._stream_task = self._spawn(self._consume_events())
        self.query_one("#input", Input).focus()
        self._spawn(self._run_health_checks())

    async def _run_health_checks(self) -> None:
        """Probe each elder's CLI at startup so missing/unauthenticated vendors
        surface immediately rather than only after the user has typed a prompt."""
        labels: dict[ElderId, str] = {
            "claude": "Claude",
            "gemini": "Gemini",
            "chatgpt": "ChatGPT",
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
            self.query_one("#input", Input).disabled = True
            self._write_notice(
                "[red]No elders available. Fix the vendor CLI setup above, "
                "then restart the app.[/red]"
            )

    def _write_notice(self, line: str) -> None:
        """Write an app-level notice (not a DebateEvent) to the stream AND the
        test-observable rendered_lines buffer."""
        self.rendered_lines.append(line)
        self.query_one("#stream", ChronologicalStream).write(line)

    async def on_unmount(self) -> None:
        if hasattr(self, "_stream_task"):
            self._stream_task.cancel()
        for task in list(self._tasks):
            task.cancel()

    async def _consume_events(self) -> None:
        async for ev in self._bus.subscribe():
            stream = self.query_one("#stream", ChronologicalStream)
            line = format_event(ev)
            if line:
                self.rendered_lines.append(line)
                stream.write(line)
            if isinstance(ev, RoundCompleted):
                self.awaiting_decision = True
            if isinstance(ev, SynthesisCompleted):
                self.is_finished = True
                self.awaiting_decision = False

    @on(Input.Submitted, "#input")
    async def _on_prompt_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt or self._debate is not None:
            return
        pack = self._pack_loader.load(self._pack_name)
        self._debate = Debate(
            id=str(uuid.uuid4()),
            prompt=prompt,
            pack=pack,
            rounds=[],
            status="in_progress",
            synthesis=None,
        )
        input_widget = self.query_one("#input", Input)
        input_widget.disabled = True
        # Move focus off the disabled Input so app-level keybindings (c/s/a/o) fire.
        self.query_one("#stream", ChronologicalStream).focus()
        self._spawn(self._service.run_round(self._debate))

    async def action_continue_round(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.awaiting_decision = False
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
        # Force all turns to agreed=True for the most recent round
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
        self._spawn(self._service.synthesize(self._debate, by=choice))


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="council")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
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

    app = CouncilApp(
        elders={
            "claude": ClaudeCodeAdapter(model=args.claude_model),
            "gemini": GeminiCLIAdapter(model=args.gemini_model),
            "chatgpt": CodexCLIAdapter(model=args.codex_model),
        },
        store=JsonFileStore(root=Path(args.store_root)),
        clock=SystemClock(),
        pack_loader=FilesystemPackLoader(root=packs_root),
        pack_name=args.pack,
    )
    app.run()
