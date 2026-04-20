import pytest

from council.domain.questions import QuestionParser


@pytest.fixture
def parser():
    return QuestionParser()


class TestNoBlock:
    def test_no_questions_header_returns_raw_and_empty(self, parser):
        raw = "Here is my answer with no questions."
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        assert cleaned == raw
        assert qs == ()

    def test_empty_input(self, parser):
        cleaned, qs = parser.parse("", from_elder="ada", round_number=1)
        assert cleaned == ""
        assert qs == ()


class TestValidBlock:
    def test_single_question_extracted(self, parser):
        raw = "My answer text.\n\nQUESTIONS:\n@kai Have you considered timeline?"
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        assert "QUESTIONS:" not in cleaned
        assert "@kai" not in cleaned
        assert cleaned.strip() == "My answer text."
        assert len(qs) == 1
        assert qs[0].from_elder == "ada"
        assert qs[0].to_elder == "kai"
        assert qs[0].text == "Have you considered timeline?"
        assert qs[0].round_number == 1

    def test_multiple_questions_extracted(self, parser):
        raw = "Answer.\nQUESTIONS:\n@kai Timeline?\n@mei Growth?"
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=2)
        assert cleaned.strip() == "Answer."
        assert len(qs) == 2
        assert {q.to_elder for q in qs} == {"kai", "mei"}

    def test_case_insensitive_header_and_elder(self, parser):
        raw = "Answer.\nquestions:\n@GEMINI Timeline?"
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        assert len(qs) == 1
        assert qs[0].to_elder == "kai"


class TestMalformedOrUnknown:
    def test_unknown_elder_ignored(self, parser):
        raw = "Answer.\nQUESTIONS:\n@bob Ignore me\n@kai Keep me"
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        # Unknown @bob doesn't match; @kai on next line should still be captured
        # because we read until a blank line or end-of-input, tolerating non-matching
        # lines as "noise inside the block".
        assert len(qs) == 1
        assert qs[0].to_elder == "kai"

    def test_self_directed_question_dropped(self, parser):
        raw = "Answer.\nQUESTIONS:\n@ada What about me?\n@kai Real question?"
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        assert len(qs) == 1
        assert qs[0].to_elder == "kai"

    def test_questions_header_without_valid_lines_yields_empty(self, parser):
        raw = "Answer.\nQUESTIONS:\n(no valid questions)"
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        # No @elder lines follow — treat as not-a-block; keep raw text.
        assert qs == ()
        assert cleaned == raw

    def test_block_terminates_at_blank_line(self, parser):
        raw = (
            "Answer.\n"
            "QUESTIONS:\n"
            "@kai Real question?\n"
            "\n"
            "@mei This is after the block and should stay in body"
        )
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        assert len(qs) == 1
        assert "should stay in body" in cleaned


class TestPositioning:
    def test_only_strips_when_block_is_at_tail(self, parser):
        raw = "QUESTIONS:\n@kai Early question\n\nBut this is the real body."
        cleaned, qs = parser.parse(raw, from_elder="ada", round_number=1)
        # The QUESTIONS block is not at the tail — keep raw, return ().
        assert qs == ()
        assert cleaned == raw
