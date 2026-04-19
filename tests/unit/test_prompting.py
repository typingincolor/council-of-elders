from datetime import datetime, timezone
import pytest
from council.domain.models import CouncilPack, Debate, ElderAnswer, ElderQuestion, Round, Turn, UserMessage
from council.domain.prompting import PromptBuilder


def _answer(elder, text, agreed=True):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def _debate(prompt="What should I do?", pack=None, rounds=None):
    return Debate(
        id="abc",
        prompt=prompt,
        pack=pack or CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=rounds or [],
        status="in_progress",
        synthesis=None,
    )


@pytest.fixture
def builder():
    return PromptBuilder()


class TestRoundOne:
    def test_includes_question(self, builder):
        prompt = builder.build(_debate(), "claude", 1)
        assert "What should I do?" in prompt

    def test_requests_converged_tag(self, builder):
        prompt = builder.build(_debate(), "claude", 1)
        assert "CONVERGED: yes" in prompt
        assert "CONVERGED: no" in prompt

    def test_includes_shared_context_when_set(self, builder):
        pack = CouncilPack(name="p", shared_context="You are my chief of staff.", personas={})
        prompt = builder.build(_debate(pack=pack), "claude", 1)
        assert "You are my chief of staff." in prompt

    def test_includes_per_elder_persona_when_set(self, builder):
        pack = CouncilPack(
            name="p",
            shared_context=None,
            personas={"claude": "You are a legal advisor.", "gemini": "You are an engineer."},
        )
        claude_prompt = builder.build(_debate(pack=pack), "claude", 1)
        gemini_prompt = builder.build(_debate(pack=pack), "gemini", 1)
        assert "legal advisor" in claude_prompt
        assert "engineer" not in claude_prompt
        assert "engineer" in gemini_prompt

    def test_no_other_advisors_section_in_round_one(self, builder):
        prompt = builder.build(_debate(), "claude", 1)
        assert "Other advisors" not in prompt


class TestRoundTwoPlus:
    def test_includes_own_previous_answer(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "My round-1 take")),
                Turn(elder="gemini", answer=_answer("gemini", "Gemini round-1")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT round-1")),
            ],
        )
        prompt = builder.build(_debate(rounds=[prev]), "claude", 2)
        assert "My round-1 take" in prompt
        assert "Your previous answer" in prompt

    def test_includes_other_advisors_answers(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "ClaudeText")),
                Turn(elder="gemini", answer=_answer("gemini", "GeminiText")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPTText")),
            ],
        )
        prompt = builder.build(_debate(rounds=[prev]), "claude", 2)
        assert "GeminiText" in prompt
        assert "ChatGPTText" in prompt
        assert "Other advisors" in prompt

    def test_excludes_failed_elders_from_other_advisors(self, builder):
        from council.domain.models import ElderError

        err = ElderError(elder="gemini", kind="timeout", detail="")
        failed = ElderAnswer(
            elder="gemini",
            text=None,
            error=err,
            agreed=None,
            created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "ClaudeText")),
                Turn(elder="gemini", answer=failed),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPTText")),
            ],
        )
        prompt = builder.build(_debate(rounds=[prev]), "claude", 2)
        assert "ChatGPTText" in prompt
        # the failed elder should not appear with empty content
        assert "[Gemini] \n" not in prompt


class TestSynthesis:
    def test_includes_all_rounds_and_prompt(self, builder):
        r1 = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "R1Claude")),
                Turn(elder="gemini", answer=_answer("gemini", "R1Gemini")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "R1ChatGPT")),
            ],
        )
        r2 = Round(
            number=2,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "R2Claude")),
                Turn(elder="gemini", answer=_answer("gemini", "R2Gemini")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "R2ChatGPT")),
            ],
        )
        prompt = builder.build_synthesis(_debate(rounds=[r1, r2]), by="claude")
        assert "What should I do?" in prompt
        for t in ("R1Claude", "R1Gemini", "R1ChatGPT", "R2Claude", "R2Gemini", "R2ChatGPT"):
            assert t in prompt

    def test_synthesis_does_not_request_converged_tag(self, builder):
        r1 = Round(number=1, turns=[])
        prompt = builder.build_synthesis(_debate(rounds=[r1]), by="claude")
        assert "CONVERGED" not in prompt


def _user_msg(text="clarify", after_round=1):
    return UserMessage(
        text=text,
        after_round=after_round,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _q(from_elder="claude", to_elder="gemini", text="why?", round_number=1):
    return ElderQuestion(
        from_elder=from_elder,
        to_elder=to_elder,
        text=text,
        round_number=round_number,
    )


class TestUserMessagesInPrompt:
    def test_round_1_omits_user_messages_section(self, builder):
        d = _debate()
        d.user_messages.append(_user_msg())
        prompt = builder.build(d, "claude", 1)
        assert "You (the asker) said" not in prompt

    def test_round_2_includes_user_messages_section(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "t1")),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[prev])
        d.user_messages.append(_user_msg("focus on timeline", after_round=1))
        prompt = builder.build(d, "claude", 2)
        assert "You (the asker) said" in prompt
        assert "focus on timeline" in prompt
        assert "After round 1" in prompt

    def test_round_3_shows_all_prior_user_messages_in_order(self, builder):
        r1 = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "t1")),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        r2 = Round(
            number=2,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "u1")),
                Turn(elder="gemini", answer=_answer("gemini", "u2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "u3")),
            ],
        )
        d = _debate(rounds=[r1, r2])
        d.user_messages.append(_user_msg("first clarification", after_round=1))
        d.user_messages.append(_user_msg("second clarification", after_round=2))
        prompt = builder.build(d, "claude", 3)
        first = prompt.find("first clarification")
        second = prompt.find("second clarification")
        assert first != -1 and second != -1
        assert first < second


class TestDirectedQuestionsInPrompt:
    def test_questions_directed_at_target_elder_are_surfaced(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(
                    elder="claude",
                    answer=_answer("claude", "t1"),
                    questions=(_q(from_elder="claude", to_elder="gemini",
                                  text="timeline?"),),
                ),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[prev])
        gemini_prompt = builder.build(d, "gemini", 2)
        assert "Questions directed at you" in gemini_prompt
        assert "From Claude" in gemini_prompt
        assert "timeline?" in gemini_prompt

    def test_other_questions_between_advisors_are_listed_separately(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(
                    elder="claude",
                    answer=_answer("claude", "t1"),
                    questions=(_q(from_elder="claude", to_elder="chatgpt",
                                  text="growth?"),),
                ),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[prev])
        gemini_prompt = builder.build(d, "gemini", 2)
        assert "Questions directed at you" not in gemini_prompt
        assert "Other questions raised between advisors" in gemini_prompt
        assert "Claude" in gemini_prompt and "ChatGPT" in gemini_prompt
        assert "growth?" in gemini_prompt

    def test_prompt_asks_for_questions_block(self, builder):
        d = _debate()
        prompt = builder.build(d, "claude", 1)
        assert "QUESTIONS:" in prompt
        assert "@" in prompt

    def test_synthesis_prompt_ignores_questions_and_user_messages(self, builder):
        r1 = Round(
            number=1,
            turns=[
                Turn(
                    elder="claude",
                    answer=_answer("claude", "t1"),
                    questions=(_q(from_elder="claude", to_elder="gemini",
                                  text="ignored in synth"),),
                ),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[r1])
        d.user_messages.append(_user_msg("ignored user msg"))
        synth = builder.build_synthesis(d, by="claude")
        assert "QUESTIONS:" not in synth
        assert "You (the asker) said" not in synth
        assert "Questions directed at you" not in synth
