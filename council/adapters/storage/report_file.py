"""Write debate reports as markdown files on disk."""

from __future__ import annotations

from pathlib import Path


class ReportFileStore:
    def __init__(self, *, root: Path) -> None:
        self._root = root

    def save(self, *, debate_id: str, markdown: str) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._root / f"{debate_id}.md"
        target.write_text(markdown, encoding="utf-8")
        return target
