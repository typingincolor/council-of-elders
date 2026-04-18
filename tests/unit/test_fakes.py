from datetime import datetime, timezone
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.events import TurnCompleted
from council.domain.models import CouncilPack, Debate, ElderAnswer


@pytest.fixture
def answer():
    return ElderAnswer(
        elder="claude",
        text="hi",
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


@pytest.fixture
def debate():
    return Debate(
        id="d1",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


class TestFakeElder:
    async def test_ask_returns_scripted_reply_in_order(self):
        e = FakeElder(elder_id="claude", replies=["first", "second"])
        assert await e.ask("q1") == "first"
        assert await e.ask("q2") == "second"

    async def test_ask_raises_when_out_of_replies(self):
        e = FakeElder(elder_id="claude", replies=["only"])
        await e.ask("q")
        with pytest.raises(AssertionError):
            await e.ask("q again")

    async def test_health_check_defaults_true(self):
        e = FakeElder(elder_id="claude", replies=[])
        assert await e.health_check() is True

    async def test_health_check_respects_flag(self):
        e = FakeElder(elder_id="claude", replies=[], healthy=False)
        assert await e.health_check() is False

    async def test_records_prompts(self):
        e = FakeElder(elder_id="claude", replies=["a", "b"])
        await e.ask("P1")
        await e.ask("P2")
        assert e.prompts == ["P1", "P2"]


class TestInMemoryStore:
    def test_save_and_load_round_trip(self, debate):
        s = InMemoryStore()
        s.save(debate)
        assert s.load("d1") is debate

    def test_load_missing_raises(self):
        s = InMemoryStore()
        with pytest.raises(KeyError):
            s.load("nope")


class TestFakeClock:
    def test_returns_initial_time_and_advances_on_demand(self):
        t0 = datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)
        c = FakeClock(now=t0)
        assert c.now() == t0
        c.advance_seconds(30)
        assert (c.now() - t0).total_seconds() == 30


class TestInMemoryBus:
    async def test_publish_and_subscribe(self, answer):
        bus = InMemoryBus()
        received = []

        async def consume():
            async for ev in bus.subscribe():
                received.append(ev)
                if len(received) == 1:
                    return

        import asyncio

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)  # let subscriber start
        await bus.publish(TurnCompleted(elder="claude", round_number=1, answer=answer))
        await task
        assert len(received) == 1
