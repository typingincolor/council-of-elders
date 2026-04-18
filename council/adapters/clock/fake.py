from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FakeClock:
    now_value: datetime

    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value

    def advance_seconds(self, seconds: float) -> None:
        self.now_value = self.now_value + timedelta(seconds=seconds)
