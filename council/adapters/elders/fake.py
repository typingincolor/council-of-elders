from __future__ import annotations

from dataclasses import dataclass, field

from council.domain.models import ElderId, Message


@dataclass
class FakeElder:
    elder_id: ElderId
    replies: list[str]
    healthy: bool = True
    conversations: list[list[Message]] = field(default_factory=list)

    async def ask(self, conversation: list[Message], *, timeout_s: float = 45.0) -> str:
        # Snapshot the conversation at call time (it mutates afterwards).
        self.conversations.append(list(conversation))
        assert self.replies, f"FakeElder({self.elder_id}) has no more scripted replies"
        return self.replies.pop(0)

    async def health_check(self) -> bool:
        return self.healthy
