from __future__ import annotations

from dataclasses import dataclass, field

from council.domain.models import ElderId


@dataclass
class FakeElder:
    elder_id: ElderId
    replies: list[str]
    healthy: bool = True
    prompts: list[str] = field(default_factory=list)

    async def ask(self, prompt: str, *, timeout_s: float = 120.0) -> str:
        self.prompts.append(prompt)
        assert self.replies, f"FakeElder({self.elder_id}) has no more scripted replies"
        return self.replies.pop(0)

    async def health_check(self) -> bool:
        return self.healthy
