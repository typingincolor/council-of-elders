from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from council.domain.models import ElderId


class CouncilInput(TextArea):
    """A TextArea where Enter submits and Ctrl+Enter inserts a newline."""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    BINDINGS = [
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
