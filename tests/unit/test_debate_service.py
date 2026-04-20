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
    # R1: silent — replies must have no CONVERGED, no questions (R1 contract).
    # R2: cross-exam — each elder asks one peer question.
    # R3: open — CONVERGED: yes drops the debate.
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "Ada R1",
                "Ada R2\n\nQUESTIONS:\n@kai Why?",
                "Ada R3\nCONVERGED: yes",
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "Kai R1",
                "Kai R2\n\nQUESTIONS:\n@ada Why?",
                "Kai R3\nCONVERGED: yes",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "Mei R1",
                "Mei R2\n\nQUESTIONS:\n@kai Why?",
                "Mei R3\nCONVERGED: yes",
            ],
        ),
    }
    return (
        DebateService(
            elders=elders,
            store=InMemoryStore(),
            clock=clock,
            bus=InMemoryBus(),
        ),
        elders,
    )


class TestRunRound:
    async def test_produces_round_with_three_turns(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        assert r.number == 1
        assert {t.elder for t in r.turns} == {"ada", "kai", "mei"}

    async def test_r1_drops_any_convergence_tag(self, svc):
        # R1 contract: agreed MUST be None. Even if a model slipped a
        # CONVERGED tag in (it hasn't in our fixture — they're silent),
        # DebateService normalises to None.
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        for t in r.turns:
            assert t.answer.agreed is None

    async def test_r3_records_convergence(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)  # R1
        await s.run_round(d)  # R2
        r3 = await s.run_round(d)  # R3
        by_elder = {t.elder: t.answer.agreed for t in r3.turns}
        assert by_elder == {"ada": True, "kai": True, "mei": True}

    async def test_r3_strips_converged_tag_from_text(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)  # R1
        await s.run_round(d)  # R2
        r3 = await s.run_round(d)
        for t in r3.turns:
            assert "CONVERGED" not in (t.answer.text or "")

    async def test_appends_round_to_debate(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)
        assert len(d.rounds) == 1

    async def test_runs_three_rounds_to_convergence(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)  # R1
        await s.run_round(d)  # R2
        r3 = await s.run_round(d)  # R3
        assert r3.number == 3
        assert d.rounds[2].converged() is True

    async def test_r2_captures_questions(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)  # R1
        r2 = await s.run_round(d)  # R2
        for t in r2.turns:
            assert len(t.questions) == 1


class TestRunRoundWithFailures:
    async def test_timeout_becomes_error_turn(self, clock):
        class TimeoutElder:
            elder_id = "kai"

            async def ask(self, prompt, *, timeout_s=120.0):
                import asyncio

                raise asyncio.TimeoutError()

            async def health_check(self):
                return True

        elders = {
            "ada": FakeElder(elder_id="ada", replies=["ok\nCONVERGED: yes"]),
            "kai": TimeoutElder(),
            "mei": FakeElder(elder_id="mei", replies=["ok\nCONVERGED: yes"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        r = await s.run_round(d)
        gem = next(t for t in r.turns if t.elder == "kai")
        assert gem.answer.text is None
        assert gem.answer.error is not None
        assert gem.answer.error.kind == "timeout"

    async def test_any_exception_becomes_nonzero_exit_error(self, clock):
        class BrokenElder:
            elder_id = "ada"

            async def ask(self, prompt, *, timeout_s=120.0):
                raise RuntimeError("kaboom")

            async def health_check(self):
                return True

        elders = {
            "ada": BrokenElder(),
            "kai": FakeElder(elder_id="kai", replies=["ok\nCONVERGED: yes"]),
            "mei": FakeElder(elder_id="mei", replies=["ok\nCONVERGED: yes"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        r = await s.run_round(d)
        c = next(t for t in r.turns if t.elder == "ada")
        assert c.answer.error is not None
        assert c.answer.error.kind == "nonzero_exit"
        assert "kaboom" in c.answer.error.detail


class TestSynthesize:
    async def test_produces_synthesis_answer(self, clock):
        elders = {
            "ada": FakeElder(
                elder_id="ada",
                replies=["Ada R1", "Final synthesized answer."],
            ),
            "kai": FakeElder(elder_id="kai", replies=["Kai R1"]),
            "mei": FakeElder(elder_id="mei", replies=["Mei R1"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)  # R1 uses one reply per elder
        ans = await s.synthesize(d, by="ada")
        assert ans.text == "Final synthesized answer."
        assert ans.elder == "ada"
        assert ans.error is None

    async def test_retries_once_on_synthesis_structural_violation(self, clock):
        # First synthesis reply has a CoT-loop signature (3 bolded headers);
        # validator triggers a single retry with a sharpened reminder; second
        # reply is clean and gets accepted.
        bad_synth = (
            "**Defining Goals**\nFirst thought...\n\n"
            "**Refining Objectives**\nSecond thought...\n\n"
            "**Focusing on Outcomes**\nThird thought..."
        )
        clean_synth = "Ship value faster by modernising our technology."
        elders = {
            "ada": FakeElder(
                elder_id="ada",
                replies=["Ada R1", bad_synth, clean_synth],
            ),
            "kai": FakeElder(elder_id="kai", replies=["Kai R1"]),
            "mei": FakeElder(elder_id="mei", replies=["Mei R1"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)
        ans = await s.synthesize(d, by="ada")
        # The retry was triggered and produced the clean second reply.
        assert ans.text == clean_synth
        # Three Ada calls total: R1 + first synth attempt + retry synth.
        assert len(elders["ada"].conversations) == 3

    async def test_synthesis_retry_ceiling_accepts_best_effort(self, clock):
        # Both synthesis attempts violate structure; the second is accepted
        # anyway (one-retry ceiling, same policy as turn-contract retry).
        bad_synth_1 = "Okay, here's the answer. Ship faster."
        bad_synth_2 = "Sure thing. Ship faster is the answer."
        elders = {
            "ada": FakeElder(
                elder_id="ada",
                replies=["Ada R1", bad_synth_1, bad_synth_2],
            ),
            "kai": FakeElder(elder_id="kai", replies=["Kai R1"]),
            "mei": FakeElder(elder_id="mei", replies=["Mei R1"]),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)
        ans = await s.synthesize(d, by="ada")
        # Accept the (still-bad) retry output — no third attempt.
        assert ans.text == bad_synth_2
        assert len(elders["ada"].conversations) == 3

    async def test_persists_debate_after_round(self, clock):
        store = InMemoryStore()
        elders = {
            "ada": FakeElder(elder_id="ada", replies=["a\nCONVERGED: yes"]),
            "kai": FakeElder(elder_id="kai", replies=["b\nCONVERGED: yes"]),
            "mei": FakeElder(elder_id="mei", replies=["c\nCONVERGED: yes"]),
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


class TestConvergenceWithQuestionsOrder:
    async def test_converged_no_before_questions_is_parsed(self, clock):
        # R3+ prompt says "CONVERGED: no, followed immediately by a
        # QUESTIONS: block" — so the CONVERGED tag appears BEFORE the
        # QUESTIONS block in the raw reply. Parser order must tolerate
        # this: agreed must resolve to False and the question captured.
        elders = {
            "ada": FakeElder(
                elder_id="ada",
                replies=[
                    "R1 Ada",
                    "R2 Ada\n\nQUESTIONS:\n@kai Why?",
                    "R3 Ada body text.\n\nCONVERGED: no\n\nQUESTIONS:\n@kai Still why?",
                ],
            ),
            "kai": FakeElder(
                elder_id="kai",
                replies=[
                    "R1 Kai",
                    "R2 Kai\n\nQUESTIONS:\n@ada Why?",
                    "R3 Kai\nCONVERGED: yes",
                ],
            ),
            "mei": FakeElder(
                elder_id="mei",
                replies=[
                    "R1 Mei",
                    "R2 Mei\n\nQUESTIONS:\n@kai Why?",
                    "R3 Mei\nCONVERGED: yes",
                ],
            ),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)  # R1
        await s.run_round(d)  # R2
        r3 = await s.run_round(d)  # R3
        claude = next(t for t in r3.turns if t.elder == "ada")
        assert claude.answer.agreed is False
        assert len(claude.questions) == 1
        assert claude.questions[0].text == "Still why?"


class TestRunRoundExtractsQuestions:
    async def test_r2_questions_block_becomes_turn_questions(self, clock):
        # R2 is where questions first appear. R1 is silent.
        elders = {
            "ada": FakeElder(
                elder_id="ada",
                replies=[
                    "Ada R1",
                    "My reply.\n\nQUESTIONS:\n@kai Timeline?",
                ],
            ),
            "kai": FakeElder(
                elder_id="kai",
                replies=[
                    "Kai R1",
                    "Kai R2\n\nQUESTIONS:\n@ada Why?",
                ],
            ),
            "mei": FakeElder(
                elder_id="mei",
                replies=[
                    "Mei R1",
                    "Mei R2\n\nQUESTIONS:\n@kai Why?",
                ],
            ),
        }
        s = DebateService(elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)  # R1
        r2 = await s.run_round(d)  # R2
        claude_turn = next(t for t in r2.turns if t.elder == "ada")
        assert len(claude_turn.questions) == 1
        assert claude_turn.questions[0].to_elder == "kai"
        assert "QUESTIONS" not in (claude_turn.answer.text or "")
        assert claude_turn.answer.text.strip() == "My reply."
