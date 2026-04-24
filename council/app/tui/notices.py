from __future__ import annotations

from typing import Literal

from textual.widgets import RichLog


class CouncilNotices:
    """Append-only notice log wrapping the `#notices` RichLog.

    Writes go to both the widget (for display) and a shared buffer
    (kept on the app for test observability via ``app.rendered_lines``).
    """

    def __init__(self, *, log: RichLog, buffer: list[str]) -> None:
        self._log = log
        self._buffer = buffer

    def write(self, line: str) -> None:
        self._buffer.append(line)
        self._log.write(line)

    def decision_hint(self, mode: Literal["r1_only", "full"]) -> None:
        """Surface keybinding affordances once per debate, at the first
        decision point. Non-intrusive but discoverable — the keybindings
        themselves are ``show=False`` in the Footer.
        """
        if mode == "r1_only":
            self.write(
                "[dim]R1 complete. [d] compare drafts (agreements/divergences)  ·  "
                "[s] synthesise  ·  [c] cross-examination round  ·  [a] finish. "
                "Read the three drafts above; synthesis tends to flatten committed "
                "specifics.[/dim]"
            )
        else:
            self.write(
                "[dim]R1+R2 complete. [d] compare drafts  ·  [s] synthesise  ·  "
                "[c] continue to another round  ·  [a] abandon.[/dim]"
            )
