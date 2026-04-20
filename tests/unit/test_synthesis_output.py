from council.domain.synthesis_output import SynthesisOutput, parse_synthesis


class TestParseSynthesis:
    def test_happy_path_all_three_sections(self):
        raw = (
            "ANSWER:\nHire one senior.\n\n"
            "WHY:\nOne senior clears blockers juniors can't.\n\n"
            "DISAGREEMENTS:\n- Ada preferred three juniors for parallelism.\n"
            "- Mei flagged onboarding cost.\n"
        )
        out = parse_synthesis(raw)
        assert out.answer == "Hire one senior."
        assert "One senior clears" in out.why
        assert len(out.disagreements) == 2
        assert "three juniors" in out.disagreements[0]
        assert "onboarding cost" in out.disagreements[1]

    def test_none_marker_yields_empty_disagreements(self):
        raw = (
            "ANSWER:\nSQLite.\n\n"
            "WHY:\n50 users is well within SQLite's range.\n\n"
            "DISAGREEMENTS:\n(none)\n"
        )
        out = parse_synthesis(raw)
        assert out.answer == "SQLite."
        assert out.disagreements == ()

    def test_missing_disagreements_section_is_empty(self):
        raw = "ANSWER:\nx\n\nWHY:\ny\n"
        out = parse_synthesis(raw)
        assert out.disagreements == ()

    def test_missing_answer_falls_back_to_full_raw(self):
        raw = "Hire one senior."
        out = parse_synthesis(raw)
        assert out.answer == "Hire one senior."
        assert out.why == ""
        assert out.disagreements == ()

    def test_disagreements_with_star_bullets(self):
        raw = (
            "ANSWER:\nok\n\n"
            "WHY:\nbecause\n\n"
            "DISAGREEMENTS:\n* first\n* second\n"
        )
        out = parse_synthesis(raw)
        assert out.disagreements == ("first", "second")

    def test_multi_line_answer_preserved(self):
        raw = (
            "ANSWER:\nFirst paragraph.\n\nSecond paragraph.\n\n"
            "WHY:\nbrief\n\n"
            "DISAGREEMENTS:\n(none)\n"
        )
        out = parse_synthesis(raw)
        assert "First paragraph." in out.answer
        assert "Second paragraph." in out.answer

    def test_case_insensitive_labels(self):
        raw = (
            "answer:\nlowercased\n\n"
            "Why:\nmixed case\n\n"
            "DISAGREEMENTS:\n- x\n"
        )
        out = parse_synthesis(raw)
        assert out.answer == "lowercased"
        assert out.why == "mixed case"
        assert out.disagreements == ("x",)

    def test_empty_disagreements_block_yields_empty(self):
        raw = "ANSWER:\nx\n\nWHY:\ny\n\nDISAGREEMENTS:\n\n"
        out = parse_synthesis(raw)
        assert out.disagreements == ()

    def test_synthesis_output_is_frozen(self):
        import dataclasses
        import pytest

        out = SynthesisOutput(answer="a", why="w", disagreements=(), raw="r")
        with pytest.raises(dataclasses.FrozenInstanceError):
            out.answer = "b"  # type: ignore[misc]
