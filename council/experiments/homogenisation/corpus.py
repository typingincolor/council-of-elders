"""Corpus loader for the homogenisation probe.

The corpus is a flat JSON list of 8 prompts spanning the shapes issue 11
lists as priorities. Stored as data (not Python) so a user can edit
prompts without touching code between runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusPrompt:
    id: str
    shape: str
    prompt: str


def load_corpus(path: Path) -> list[CorpusPrompt]:
    """Load the homogenisation probe corpus from a JSON file.

    Raises KeyError if any prompt is missing required fields, so a
    malformed file fails fast at startup rather than mid-run.
    """
    data = json.loads(path.read_text())
    return [CorpusPrompt(id=p["id"], shape=p["shape"], prompt=p["prompt"]) for p in data["prompts"]]
