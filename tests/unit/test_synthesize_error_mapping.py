"""DebateService.synthesize() must preserve structured adapter error kinds,
not flatten them all to nonzero_exit."""

from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders._subprocess import ElderSubprocessError
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate


def _debate():
    return Debate(
        id="d1",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


class QuotaExhaustedElder:
    elder_id = "gemini"

    async def ask(self, prompt, *, timeout_s=45.0):
        raise ElderSubprocessError("quota_exhausted", "daily limit reached")

    async def health_check(self):
        return True


async def test_synthesize_preserves_structured_error_kind():
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["r1\nCONVERGED: yes"]),
        "gemini": QuotaExhaustedElder(),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["r1\nCONVERGED: yes"]),
    }
    s = DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
    )
    d = _debate()
    # Prime a round so synthesize has context.
    await s.run_round(d)
    # Ask Gemini (the one wired to raise) to synthesise.
    ans = await s.synthesize(d, by="gemini")
    assert ans.error is not None
    assert ans.error.kind == "quota_exhausted"
    assert ans.error.detail == "daily limit reached"


async def test_synthesize_unstructured_exception_still_falls_back_to_nonzero_exit():
    class BoomElder:
        elder_id = "claude"

        async def ask(self, prompt, *, timeout_s=45.0):
            raise RuntimeError("generic boom")

        async def health_check(self):
            return True

    elders = {
        "claude": BoomElder(),
        "gemini": FakeElder(elder_id="gemini", replies=["r1\nCONVERGED: yes"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["r1\nCONVERGED: yes"]),
    }
    s = DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
    )
    d = _debate()
    await s.run_round(d)
    ans = await s.synthesize(d, by="claude")
    assert ans.error is not None
    assert ans.error.kind == "nonzero_exit"
    assert "generic boom" in ans.error.detail
