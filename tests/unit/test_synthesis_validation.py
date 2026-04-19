from council.domain.synthesis_validation import (
    SynthesisOk,
    SynthesisValidator,
    SynthesisViolation,
)


def _v():
    return SynthesisValidator()


class TestEmpty:
    def test_empty_output_is_violation(self):
        r = _v().validate("")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "empty_output"

    def test_whitespace_only_is_violation(self):
        r = _v().validate("   \n\n   ")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "empty_output"


class TestPreamble:
    def test_okay_preamble(self):
        r = _v().validate("Okay, the answer is to ship faster.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "preamble"

    def test_heres_the_answer_preamble(self):
        r = _v().validate("Here's the answer: ship faster.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "preamble"

    def test_let_me_preamble(self):
        r = _v().validate("Let me explain: the approach is incremental.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "preamble"

    def test_substantive_first_word_is_fine(self):
        r = _v().validate("Ship value faster and safer by modernising our technology.")
        assert isinstance(r, SynthesisOk)

    def test_mid_body_okay_is_not_preamble(self):
        # "Okay" appearing mid-text after a substantive start is fine.
        r = _v().validate("Ship value faster. Okay, we need to consider quality too.")
        assert isinstance(r, SynthesisOk)


class TestConvergedTagLeakage:
    def test_converged_yes_leakage(self):
        r = _v().validate("Ship faster.\n\nCONVERGED: yes")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "converged_tag_leakage"

    def test_converged_no_leakage(self):
        r = _v().validate("Ship faster. CONVERGED: no")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "converged_tag_leakage"


class TestRepeatedBoldedHeaders:
    def test_three_bolded_headers_triggers_cot_loop_detection(self):
        text = (
            "**Defining Goals**\nsome text\n"
            "**Refining the Core Objective**\nmore text\n"
            "**Focusing on Program Outcomes**\neven more"
        )
        r = _v().validate(text)
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "cot_loop_headers"

    def test_two_bolded_headers_is_tolerated(self):
        text = "**Quick note** first. Then **another point** here."
        r = _v().validate(text)
        # 2 headers is below threshold; other detectors may fire if pattern
        # matches but in this case it's fine.
        assert isinstance(r, SynthesisOk)


class TestDraftLabels:
    def test_goal_draft_label(self):
        r = _v().validate("Goal: ship faster.\n\nThe approach is incremental.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "draft_label"

    def test_step_label(self):
        r = _v().validate("Start by modernising the stack.\n\nStep 1: pick the biggest pain.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "draft_label"

    def test_defining_bold_label(self):
        # Using a substantive opening (not matching any preamble pattern)
        # so that the draft_label detector is the one that fires.
        r = _v().validate(
            "Ship faster by modernising the stack.\n\n**Defining Priorities**\nStart here."
        )
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "draft_label"


class TestAdvisorMentions:
    def test_two_mentions_triggers(self):
        r = _v().validate("Ship value faster. This matches what Claude and Gemini argued.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "advisor_mentions"

    def test_single_legitimate_mention_is_tolerated(self):
        # A single stray "claude" (e.g. part of a technical term or in
        # a direct quote) doesn't fire — threshold is 2.
        r = _v().validate("Ship faster. The claude-flavoured approach is one option.")
        assert isinstance(r, SynthesisOk)

    def test_the_debate_mention(self):
        r = _v().validate("Ship value faster. The debate surfaced that Gemini pushed back.")
        assert isinstance(r, SynthesisViolation)
        assert r.reason == "advisor_mentions"


class TestMidLoopTruncation:
    def test_first_header_repeats_at_end(self):
        text = (
            "**Defining Goals**\nIntro.\n\n"
            "**Exploring Options**\nMiddle.\n\n"
            "**Defining Goals**\nLooping back..."
        )
        r = _v().validate(text)
        assert isinstance(r, SynthesisViolation)
        # cot_loop_headers fires first because there are 3+ headers;
        # the mid-loop heuristic is the backstop for 2-header cases.
        assert r.reason == "cot_loop_headers"


class TestOkayCases:
    def test_tight_headline_passes(self):
        r = _v().validate(
            "Ship value faster and safer by modernising our technology and removing friction."
        )
        assert isinstance(r, SynthesisOk)

    def test_concrete_list_passes(self):
        text = (
            "Modernise the stack, remove SDLC friction, and align teams.\n"
            "- Start with the Order Platform.\n"
            "- Exit the Perl monolith.\n"
            "- Drive cycle time below 5 days."
        )
        r = _v().validate(text)
        assert isinstance(r, SynthesisOk)

    def test_bold_emphasis_on_single_phrase_passes(self):
        # A single **emphasis** phrase shouldn't fire the repeated-header
        # detector.
        text = "The goal is to **ship faster** while keeping quality high."
        r = _v().validate(text)
        assert isinstance(r, SynthesisOk)
