from __future__ import annotations

from textual.widgets import RichLog

from council.domain.events import (
    DebateAbandoned,
    DebateEvent,
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import ElderId

_LABELS: dict[ElderId, str] = {"claude": "Claude", "gemini": "Gemini", "chatgpt": "ChatGPT"}
_COLORS: dict[ElderId, str] = {"claude": "magenta", "gemini": "cyan", "chatgpt": "green"}


def format_event(event: DebateEvent) -> str:
    """Produce a Rich-markup-formatted line for an event."""
    if isinstance(event, TurnStarted):
        c = _COLORS[event.elder]
        return (
            f"[dim][{c}]{_LABELS[event.elder]}[/] is thinking… (round {event.round_number})[/dim]"
        )
    if isinstance(event, TurnCompleted):
        c = _COLORS[event.elder]
        tag = ""
        if event.answer.agreed is True:
            tag = " [green](converged)[/green]"
        elif event.answer.agreed is False:
            tag = " [yellow](dissenting)[/yellow]"
        return f"[bold {c}][{_LABELS[event.elder]}][/]{tag}\n{event.answer.text or ''}\n"
    if isinstance(event, TurnFailed):
        c = _COLORS[event.elder]
        return (
            f"[bold {c}][{_LABELS[event.elder]}][/] "
            f"[red]ERROR {event.error.kind}[/red]: {event.error.detail}"
        )
    if isinstance(event, RoundCompleted):
        return f"[dim]— Round {event.round.number} complete —[/dim]"
    if isinstance(event, SynthesisCompleted):
        return (
            f"[bold yellow][Synthesis by {_LABELS[event.answer.elder]}][/]\n"
            f"{event.answer.text or ''}\n"
        )
    if isinstance(event, DebateAbandoned):
        return "[dim]— Debate abandoned —[/dim]"
    return ""


class ChronologicalStream(RichLog):
    def __init__(self, **kwargs):
        super().__init__(markup=True, wrap=True, highlight=False, **kwargs)

    def write_event(self, event: DebateEvent) -> None:
        line = format_event(event)
        if line:
            self.write(line)
