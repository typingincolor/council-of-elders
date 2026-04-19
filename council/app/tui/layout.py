"""Responsive layout mode selection for the council TUI.

Three-column mode is used when the terminal is wide enough to give each elder
at least 80 readable characters. Below that, tabs.
"""

from __future__ import annotations

from typing import Literal

LayoutMode = Literal["tabs", "columns"]

MIN_WIDTH_PER_ELDER: int = 80
MIN_WIDTH_3COL: int = 3 * MIN_WIDTH_PER_ELDER  # 240


def pick_layout(width: int, forced: LayoutMode | None) -> LayoutMode:
    """Decide whether to render tabs or three columns.

    If `forced` is set (by the user toggling `f`), that choice wins.
    Otherwise we pick based on the terminal width.
    """
    if forced is not None:
        return forced
    return "columns" if width >= MIN_WIDTH_3COL else "tabs"
