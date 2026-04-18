from __future__ import annotations

from council.domain.models import Debate


class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, Debate] = {}

    def save(self, debate: Debate) -> None:
        self._data[debate.id] = debate

    def load(self, debate_id: str) -> Debate:
        return self._data[debate_id]
