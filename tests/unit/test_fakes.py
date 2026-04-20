from datetime import datetime, timezone
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.events import TurnCompleted
from council.domain.models import CouncilPack, Debate, ElderAnswer, Message


@pytest.fixture
def answer():
    return ElderAnswer(
        elder="ada",
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


def _c(text: str) -> list[Message]:
    return [Message("user", text)]


class TestFakeElder:
    async def test_ask_returns_scripted_reply_in_order(self):
        e = FakeElder(elder_id="ada", replies=["first", "second"])
        assert await e.ask(_c("q1")) == "first"
        assert await e.ask(_c("q2")) == "second"

    async def test_ask_raises_when_out_of_replies(self):
        e = FakeElder(elder_id="ada", replies=["only"])
        await e.ask(_c("q"))
        with pytest.raises(AssertionError):
            await e.ask(_c("q again"))

    async def test_health_check_defaults_true(self):
        e = FakeElder(elder_id="ada", replies=[])
        assert await e.health_check() is True

    async def test_health_check_respects_flag(self):
        e = FakeElder(elder_id="ada", replies=[], healthy=False)
        assert await e.health_check() is False

    async def test_records_conversations(self):
        e = FakeElder(elder_id="ada", replies=["a", "b"])
        await e.ask(_c("P1"))
        await e.ask(_c("P2"))
        assert e.conversations == [[Message("user", "P1")], [Message("user", "P2")]]


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
        await bus.publish(TurnCompleted(elder="ada", round_number=1, answer=answer))
        await task
        assert len(received) == 1
