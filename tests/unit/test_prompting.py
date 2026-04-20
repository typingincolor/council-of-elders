from datetime import datetime, timezone

import pytest

from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderQuestion,
    Round,
    Turn,
    UserMessage,
)
from council.domain.prompting import PromptBuilder


def _answer(elder, text, agreed=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def _debate(prompt="What should I do?", pack=None, rounds=None, user_messages=None):
    d = Debate(
        id="abc",
        prompt=prompt,
        pack=pack or CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=rounds or [],
        status="in_progress",
        synthesis=None,
    )
    if user_messages:
        d.user_messages.extend(user_messages)
    return d


def _r1():
    return Round(
        number=1,
        turns=[
            Turn(elder="claude", answer=_answer("claude", "Claude R1")),
            Turn(elder="gemini", answer=_answer("gemini", "Gemini R1")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT R1")),
        ],
    )


def _r2_with_questions():
    q = ElderQuestion(from_elder="gemini", to_elder="claude", text="Why SSE?", round_number=2)
    q2 = ElderQuestion(
        from_elder="chatgpt", to_elder="gemini", text="What about growth?", round_number=2
    )
    return Round(
        number=2,
        turns=[
            Turn(elder="claude", answer=_answer("claude", "Claude R2")),
            Turn(elder="gemini", answer=_answer("gemini", "Gemini R2"), questions=(q,)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT R2"), questions=(q2,)),
        ],
    )


@pytest.fixture
def builder():
    return PromptBuilder()


class TestBuildSystemMessage:
    def test_empty_when_no_persona_or_context(self, builder):
        assert builder.build_system_message(_debate(), "claude") == ""

    def test_persona_only(self, builder):
        pack = CouncilPack(name="p", shared_context=None, personas={"claude": "You are a lawyer."})
        assert "lawyer" in builder.build_system_message(_debate(pack=pack), "claude")

    def test_shared_context_only(self, builder):
        pack = CouncilPack(name="p", shared_context="You are my chief of staff.", personas={})
        out = builder.build_system_message(_debate(pack=pack), "claude")
        assert "chief of staff" in out

    def test_both_combined(self, builder):
        pack = CouncilPack(name="p", shared_context="Chief.", personas={"claude": "Lawyer."})
        out = builder.build_system_message(_debate(pack=pack), "claude")
        assert "Lawyer" in out
        assert "Chief" in out

    def test_per_elder_persona_does_not_leak(self, builder):
        pack = CouncilPack(
            name="p",
            shared_context=None,
            personas={"claude": "Lawyer.", "gemini": "Engineer."},
        )
        assert "Lawyer" in builder.build_system_message(_debate(pack=pack), "claude")
        assert "Engineer" not in builder.build_system_message(_debate(pack=pack), "claude")


class TestBuildRoundOneUser:
    def test_includes_question(self, builder):
        out = builder.build_round_1_user(_debate("Should I ship?"))
        assert "Should I ship?" in out

    def test_forbids_peer_questions_but_allows_reasoning_interrogatives(self, builder):
        # Rewrite replaces the overbroad "do not ask questions" with a
        # peer-directed ban while carving out ordinary interrogatives used
        # inside the model's own reasoning.
        out = builder.build_round_1_user(_debate())
        low = out.lower()
        assert "peer-directed question" in low
        assert "interrogative sentences inside your own reasoning" in low

    def test_reserves_literal_tag_strings(self, builder):
        # New rule: the reply must not contain `CONVERGED:` or `QUESTIONS:`
        # as literal strings. The instruction itself uses them to reserve
        # the strings — so they ARE present in the prompt (correct), just
        # not as a directive to emit.
        out = builder.build_round_1_user(_debate())
        assert "literal strings CONVERGED:" in out or "CONVERGED: or QUESTIONS:" in out

    def test_positive_framing_asks_for_substantive_depth(self, builder):
        # Rewrite replaces the brevity-priming "silent initial take" with
        # a positive request for depth at natural reasoning length.
        out = builder.build_round_1_user(_debate())
        low = out.lower()
        assert "fully and directly" in low or "real substantive answer" in low
        assert "normal level of reasoning" in low or "cross-examination" in low

    def test_first_token_anchor(self, builder):
        # Consistency with R3+ pattern.
        out = builder.build_round_1_user(_debate())
        assert "Begin with the first word" in out


class TestBuildRoundTwoUser:
    def test_includes_other_advisors(self, builder):
        out = builder.build_round_2_user(_debate(rounds=[_r1()]), "claude")
        assert "Gemini R1" in out
        assert "ChatGPT R1" in out
        assert "Claude R1" not in out  # elder doesn't need to see its own

    def test_requires_exactly_one_question(self, builder):
        out = builder.build_round_2_user(_debate(rounds=[_r1()]), "claude")
        assert "QUESTIONS:" in out
        assert "exactly one" in out.lower() or "one question" in out.lower()

    def test_does_not_request_convergence(self, builder):
        out = builder.build_round_2_user(_debate(rounds=[_r1()]), "claude")
        # There should be no "CONVERGED: yes/no" directive (only possibly
        # a "do not emit CONVERGED" negative instruction).
        assert "CONVERGED: yes" not in out
        assert "CONVERGED: no" not in out

    def test_includes_user_messages_when_present(self, builder):
        um = UserMessage(
            text="please focus on timeline",
            after_round=1,
            created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        )
        d = _debate(rounds=[_r1()], user_messages=[um])
        out = builder.build_round_2_user(d, "claude")
        assert "focus on timeline" in out


class TestBuildRoundNUser:
    def test_includes_previous_round_other_advisors(self, builder):
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        assert "Gemini R2" in out
        assert "ChatGPT R2" in out

    def test_omits_own_previous_answer(self, builder):
        # Previous answer lives in conversation history; it should NOT be
        # re-stuffed into the user message.
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        assert "Claude R2" not in out

    def test_includes_directed_questions(self, builder):
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        assert "Why SSE?" in out

    def test_includes_peer_questions(self, builder):
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        # Claude sees chatgpt→gemini question as peer cross-talk.
        assert "What about growth?" in out

    def test_convergence_contract_wording(self, builder):
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        assert "CONVERGED: yes" in out
        assert "CONVERGED: no" in out
        assert "QUESTIONS:" in out

    def test_requires_substantive_body_before_tag(self, builder):
        # Rewrite forbids a reply that is only the tag (fixes empty-body bug).
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        low = out.lower()
        assert "substantive reply first" in low or "substantive reply" in low
        assert "never reply with only a tag" in low or "only a tag" in low

    def test_uses_operational_convergence_criterion(self, builder):
        # Rewrite replaces introspective "would not change your position"
        # with operational "no further peer answer needed".
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        low = out.lower()
        assert "further answer from a peer" in low or "further peer answer" in low
        # The old introspective phrasing must be gone.
        assert "would not change your position" not in low

    def test_bans_literal_tag_strings_in_body(self, builder):
        # Prevents stray-header shadowing when the model quotes a peer's tag.
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        assert "reserve those headers for the closing block" in out

    def test_illustrative_tag_lines_are_flush_left(self, builder):
        # Prevents indent mimicry. The illustrative CONVERGED/QUESTIONS lines
        # in the prompt must appear at column 0, not indented.
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        lines = out.splitlines()
        # The three-line closing template must appear as three consecutive
        # flush-left lines.
        assert "CONVERGED: no" in lines
        assert "QUESTIONS:" in lines
        # And explicitly no indented versions.
        assert "    QUESTIONS:" not in out
        assert "    CONVERGED:" not in out

    def test_forbids_text_after_tag(self, builder):
        # Prevents trailing sign-offs breaking the last-non-blank-line parse.
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_round_n_user(d, "claude", 3)
        low = out.lower()
        assert "absolute final lines" in low
        assert "no sign-offs" in low or "do not add sign-offs" in low or "sign-offs" in low


class TestBuildRetryReminder:
    def test_contains_violation_reason(self, builder):
        out = builder.build_retry_reminder("Round 2 requires exactly one question.")
        assert "Round 2 requires exactly one question." in out

    def test_asks_for_re_send(self, builder):
        out = builder.build_retry_reminder("anything")
        low = out.lower()
        assert "re-send" in low or "resend" in low or "again" in low


class TestBuildSynthesis:
    def test_includes_all_rounds(self, builder):
        d = _debate(rounds=[_r1(), _r2_with_questions()])
        out = builder.build_synthesis(d, by="claude")
        assert "Claude R1" in out
        assert "Gemini R2" in out

    def test_includes_original_question(self, builder):
        d = _debate(prompt="What to ship?", rounds=[_r1()])
        out = builder.build_synthesis(d, by="claude")
        assert "What to ship?" in out

    def test_anchors_to_user_question_shape(self, builder):
        # The ANSWER section must calibrate to the user's ask.
        out = builder.build_synthesis(_debate("Give me one sentence."), by="claude")
        low = out.lower()
        assert "genuinely punchy" in low or "shortest response that fully answers" in low
        assert "no preamble" in low

    def test_severs_length_from_transcript(self, builder):
        # Anti-mimicry: calibrate to user, not to transcript length.
        out = builder.build_synthesis(_debate(), by="claude")
        low = out.lower()
        assert "calibrate to the user" in low
        assert "not to the transcript" in low

    def test_requires_synthesis_not_selection(self, builder):
        out = builder.build_synthesis(_debate(), by="claude")
        low = out.lower()
        assert "synthesize, do not select" in low or "synthesise, do not select" in low
        assert "single advisor's wording wholesale" in low

    def test_requests_structured_answer_why_disagreements(self, builder):
        # Stage 4 contract: synthesis emits three labelled sections
        # (Answer / Why / Disagreements) so the user-facing deliverable
        # preserves decision-relevant divergence.
        out = builder.build_synthesis(_debate(), by="claude")
        assert "ANSWER:" in out
        assert "WHY:" in out
        assert "DISAGREEMENTS:" in out
        assert "decision-relevant" in out.lower()
        # (none) marker documented for harmonious debates.
        assert "(none)" in out

    def test_forbids_convergence_tag(self, builder):
        out = builder.build_synthesis(_debate(), by="claude")
        assert "converged" in out.lower()
        # Must explicitly say DO NOT append the tag.
        assert "do not append" in out.lower() or "not append a converged" in out.lower()
