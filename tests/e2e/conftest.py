"""Helpers used by e2e tests."""

from __future__ import annotations


def pane_lines(app, elder_key: str) -> str:
    """Return the history text of a specific ElderPaneWidget by elder key.

    `elder_key` is one of "ada", "kai", "mei", or "synthesis".
    Apps that expose a CouncilView must store it on `app._view`.
    """
    view = getattr(app, "_view", None)
    if view is None:
        raise AssertionError("app has no _view attribute; helper expects CouncilApp-shaped apps")
    pane = view.pane(elder_key)
    return pane.history_text()
