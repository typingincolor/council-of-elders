from datetime import datetime, timezone
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.events import UserMessageReceived
from council.domain.models import CouncilPack, Debate


def _fresh_debate():
    return Debate(
        id="d1",
        prompt="What should I do?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


@pytest.fixture
def clock():
    return FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc))


@pytest.fixture
def svc(clock):
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["Claude round-1\nCONVERGED: yes"]),
        "gemini": FakeElder(elder_id="gemini", replies=["Gemini round-1\nCONVERGED: no"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["ChatGPT round-1\nCONVERGED: yes"]),
    }
    return DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=clock,
        bus=InMemoryBus(),
    ), elders


class TestRunRound:
    async def test_produces_round_with_three_turns(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        assert r.number == 1
        assert {t.elder for t in r.turns} == {"claude", "gemini", "chatgpt"}

    async def test_strips_converged_tag_from_answers(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        claude_turn = next(t for t in r.turns if t.elder == "claude")
        assert "CONVERGED" not in (claude_turn.answer.text or "")
        assert claude_turn.answer.agreed is True

    async def test_records_agreement_status(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        by_elder = {t.elder: t.answer.agreed for t in r.turns}
        assert by_elder["claude"] is True
        assert by_elder["gemini"] is False
        assert by_elder["chatgpt"] is True

    async def test_appends_round_to_debate(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)
        assert len(d.rounds) == 1

    async def test_runs_multiple_rounds(self, clock):
        elders = {
            "claude": FakeElder(
                elder_id="claude",
                replies=[
                    "R1 Claude\nCONVERGED: no",
                    "R2 Claude\nCONVERGED: yes",
                ],
            ),
            "gemini": FakeElder(
                elder_id="gemini",
                replies=[
                    "R1 Gemini\nCONVERGED: no",
                    "R2 Gemini\nCONVERGED: yes",
                ],
            ),
            "chatgpt": FakeElder(
                elder_id="chatgpt",
                replies=[
                    "R1 ChatGPT\nCONVERGED: no",
                    "R2 ChatGPT\nCONVERGED: yes",
                ],
            ),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        r1 = await s.run_round(d)
        r2 = await s.run_round(d)
        assert r1.number == 1
        assert r2.number == 2
        assert d.rounds[1].converged() is True


class TestRunRoundWithFailures:
    async def test_timeout_becomes_error_turn(self, clock):
        class TimeoutElder:
            elder_id = "gemini"

            async def ask(self, prompt, *, timeout_s=120.0):
                import asyncio

                raise asyncio.TimeoutError()

            async def health_check(self):
                return True

        elders = {
            "claude": FakeElder(elder_id="claude", replies=["ok\nCONVERGED: yes"]),
            "gemini": TimeoutElder(),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=["ok\nCONVERGED: yes"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        r = await s.run_round(d)
        gem = next(t for t in r.turns if t.elder == "gemini")
        assert gem.answer.text is None
        assert gem.answer.error is not None
        assert gem.answer.error.kind == "timeout"

    async def test_any_exception_becomes_nonzero_exit_error(self, clock):
        class BrokenElder:
            elder_id = "claude"

            async def ask(self, prompt, *, timeout_s=120.0):
                raise RuntimeError("kaboom")

            async def health_check(self):
                return True

        elders = {
            "claude": BrokenElder(),
            "gemini": FakeElder(elder_id="gemini", replies=["ok\nCONVERGED: yes"]),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=["ok\nCONVERGED: yes"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        r = await s.run_round(d)
        c = next(t for t in r.turns if t.elder == "claude")
        assert c.answer.error is not None
        assert c.answer.error.kind == "nonzero_exit"
        assert "kaboom" in c.answer.error.detail


class TestSynthesize:
    async def test_produces_synthesis_answer(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)
        # Prepare a synthesizer elder with a scripted synthesis reply
        s.elders["claude"].replies.append("Final synthesized answer.")
        ans = await s.synthesize(d, by="claude")
        assert ans.text == "Final synthesized answer."
        assert ans.elder == "claude"
        assert ans.error is None

    async def test_persists_debate_after_round(self, clock):
        store = InMemoryStore()
        elders = {
            "claude": FakeElder(elder_id="claude", replies=["a\nCONVERGED: yes"]),
            "gemini": FakeElder(elder_id="gemini", replies=["b\nCONVERGED: yes"]),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=["c\nCONVERGED: yes"]),
        }
        s = DebateService(elders=elders, store=store, clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)
        assert store.load("d1") is d


class TestAddUserMessage:
    async def test_appends_saves_and_publishes(self, svc):
        s, _ = svc
        d = _fresh_debate()
        # Run a round so user_messages.after_round = 1 makes sense
        await s.run_round(d)
        collected: list = []

        async def collect():
            async for ev in s.bus.subscribe():
                collected.append(ev)

        import asyncio

        task = asyncio.create_task(collect())
        await asyncio.sleep(0)
        msg = await s.add_user_message(d, "please focus on timeline")
        await asyncio.sleep(0)
        task.cancel()
        assert msg.text == "please focus on timeline"
        assert msg.after_round == 1
        assert d.user_messages == [msg]
        assert any(isinstance(ev, UserMessageReceived) and ev.message is msg for ev in collected)

    async def test_strips_whitespace(self, svc):
        s, _ = svc
        d = _fresh_debate()
        msg = await s.add_user_message(d, "   with space  \n")
        assert msg.text == "with space"


class TestRunRoundExtractsQuestions:
    async def test_questions_block_becomes_turn_questions(self, clock):
        elders = {
            "claude": FakeElder(
                elder_id="claude",
                replies=["My reply.\n\nQUESTIONS:\n@gemini Timeline?\n\nCONVERGED: no"],
            ),
            "gemini": FakeElder(
                elder_id="gemini",
                replies=["Mine\nCONVERGED: yes"],
            ),
            "chatgpt": FakeElder(
                elder_id="chatgpt",
                replies=["Mine\nCONVERGED: yes"],
            ),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        r = await s.run_round(d)
        claude_turn = next(t for t in r.turns if t.elder == "claude")
        assert len(claude_turn.questions) == 1
        assert claude_turn.questions[0].to_elder == "gemini"
        assert "QUESTIONS" not in (claude_turn.answer.text or "")
        assert claude_turn.answer.text.strip() == "My reply."
