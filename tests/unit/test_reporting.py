from datetime import datetime, timezone

import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderQuestion,
    Round,
    Turn,
    UserMessage,
)
from council.domain.reporting import (
    ReportBuilder,
    _demote_markdown_headings,
    _truncate_prompt,
)


def _answer(elder, text="x", agreed=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _debate_with_history():
    r1 = Round(
        number=1,
        turns=[
            Turn(elder="claude", answer=_answer("claude", "C R1")),
            Turn(elder="gemini", answer=_answer("gemini", "G R1")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "X R1")),
        ],
    )
    q1 = ElderQuestion(from_elder="claude", to_elder="gemini", text="Why SSE?", round_number=2)
    q2 = ElderQuestion(from_elder="gemini", to_elder="chatgpt", text="Growth?", round_number=2)
    q3 = ElderQuestion(from_elder="chatgpt", to_elder="claude", text="Latency?", round_number=2)
    r2 = Round(
        number=2,
        turns=[
            Turn(
                elder="claude",
                answer=_answer("claude", "C R2"),
                questions=(q1,),
            ),
            Turn(
                elder="gemini",
                answer=_answer("gemini", "G R2"),
                questions=(q2,),
            ),
            Turn(
                elder="chatgpt",
                answer=_answer("chatgpt", "X R2"),
                questions=(q3,),
            ),
        ],
    )
    r3 = Round(
        number=3,
        turns=[
            Turn(elder="claude", answer=_answer("claude", "C R3", agreed=True)),
            Turn(elder="gemini", answer=_answer("gemini", "G R3", agreed=True)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "X R3", agreed=True)),
        ],
    )
    return Debate(
        id="dbg",
        prompt="Should we ship?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[r1, r2, r3],
        status="synthesized",
        synthesis=_answer("claude", "Final answer.", agreed=None),
    )


@pytest.fixture
def builder():
    return ReportBuilder()


class TestTruncatePrompt:
    def test_short_single_line_unchanged(self):
        short, truncated = _truncate_prompt("Should I ship?")
        assert short == "Should I ship?"
        assert truncated is False

    def test_long_multiline_returns_first_sentence(self):
        p = (
            "Should I ship the new feature? There's a lot of context below.\n\n"
            "Here is pasted source material that goes on and on and on..."
        )
        short, truncated = _truncate_prompt(p)
        assert short == "Should I ship the new feature?"
        assert truncated is True

    def test_first_line_longer_than_limit_gets_ellipsis(self):
        p = "a" * 500
        short, truncated = _truncate_prompt(p, limit=50)
        assert len(short) <= 52  # 50 + "…"
        assert short.endswith("…")
        assert truncated is True

    def test_long_single_line_with_no_sentence_break(self):
        p = "word " * 100
        short, truncated = _truncate_prompt(p)
        assert truncated is True


class TestDemoteMarkdownHeadings:
    def test_demotes_two_levels_by_default(self):
        md = "## Title\ntext\n### Sub\nmore"
        out = _demote_markdown_headings(md)
        assert out == "#### Title\ntext\n##### Sub\nmore"

    def test_clamps_at_six(self):
        md = "##### deeper\n###### deepest"
        out = _demote_markdown_headings(md)
        assert out == "###### deeper\n###### deepest"

    def test_leaves_code_fences_alone(self):
        md = "normal\n```\n## not-a-heading\n```\n## real-heading"
        out = _demote_markdown_headings(md)
        lines = out.splitlines()
        assert lines[2] == "## not-a-heading"  # inside fence — unchanged
        assert lines[4] == "#### real-heading"  # outside fence — demoted

    def test_ignores_hash_without_space(self):
        md = "#tag-not-heading\n##also-not\n## but this one yes"
        out = _demote_markdown_headings(md)
        assert out.startswith("#tag-not-heading\n##also-not\n")
        assert "#### but this one yes" in out

    def test_custom_levels(self):
        md = "# Heading"
        out = _demote_markdown_headings(md, levels=3)
        assert out == "#### Heading"


class TestBuildMetadataSection:
    def test_includes_round_count(self, builder):
        md = builder.build_metadata_section(_debate_with_history())
        assert "**Rounds:** 3" in md

    def test_includes_question_count(self, builder):
        md = builder.build_metadata_section(_debate_with_history())
        assert "**Questions asked:** 3" in md

    def test_includes_question_list(self, builder):
        md = builder.build_metadata_section(_debate_with_history())
        assert "Claude → Gemini" in md
        assert "Why SSE?" in md
        assert "Gemini → ChatGPT" in md
        assert "ChatGPT → Claude" in md

    def test_includes_convergence_summary(self, builder):
        md = builder.build_metadata_section(_debate_with_history())
        assert "round 3" in md.lower()

    def test_includes_timeline_table(self, builder):
        md = builder.build_metadata_section(_debate_with_history())
        assert "| R1 |" in md
        assert "| R2 |" in md
        assert "| R3 |" in md
        # R3 should show "yes" under all three.
        assert "| R3 | yes | yes | yes |" in md

    def test_includes_user_messages_section_when_present(self, builder):
        d = _debate_with_history()
        d.user_messages.append(
            UserMessage(
                text="focus on timeline",
                after_round=1,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            )
        )
        md = builder.build_metadata_section(d)
        assert "User messages" in md
        assert "focus on timeline" in md

    def test_no_user_messages_section_when_empty(self, builder):
        md = builder.build_metadata_section(_debate_with_history())
        assert "User messages" not in md


class TestBuildFinalPositionsSection:
    def test_renders_each_elder_with_convergence_label(self, builder):
        md = builder.build_final_positions_section(_debate_with_history())
        assert "### Claude — _CONVERGED: yes_" in md
        assert "### Gemini — _CONVERGED: yes_" in md
        assert "### ChatGPT — _CONVERGED: yes_" in md

    def test_includes_each_elders_last_round_text(self, builder):
        md = builder.build_final_positions_section(_debate_with_history())
        # R3 final-round answers are "C R3", "G R3", "X R3" from the fixture.
        assert "C R3" in md
        assert "G R3" in md
        assert "X R3" in md

    def test_empty_when_no_rounds(self, builder):
        d = Debate(
            id="empty",
            prompt="?",
            pack=CouncilPack(name="bare", shared_context=None, personas={}),
            rounds=[],
            status="in_progress",
            synthesis=None,
        )
        assert builder.build_final_positions_section(d) == ""


class TestBuildNarrativePrompt:
    def test_asks_about_process_not_answer(self, builder):
        d = _debate_with_history()
        out = builder.build_narrative_prompt(d, d.synthesis)
        low = out.lower()
        assert "do not repeat" in low or "don't repeat" in low

    def test_asks_for_past_tense_third_person(self, builder):
        d = _debate_with_history()
        out = builder.build_narrative_prompt(d, d.synthesis)
        assert "past tense" in out.lower()
        assert "third-person" in out.lower() or "third person" in out.lower()

    def test_contains_consensus_check_directive(self, builder):
        d = _debate_with_history()
        out = builder.build_narrative_prompt(d, d.synthesis)
        low = out.lower()
        # Must explicitly flag that CONVERGED: yes can be false consensus.
        assert "consensus" in low
        assert "final-round" in low or "word-for-word" in low
        assert "procedural" in low or "real consensus" in low


class TestAssembleReportMarkdown:
    def test_contains_synthesis_text(self, builder):
        d = _debate_with_history()
        md = builder.assemble_report_markdown(
            d, d.synthesis, "Narrative goes here.", synthesiser="claude"
        )
        assert "Final answer." in md

    def test_contains_narrative_section(self, builder):
        d = _debate_with_history()
        md = builder.assemble_report_markdown(
            d, d.synthesis, "Narrative goes here.", synthesiser="claude"
        )
        assert "## Narrative" in md
        assert "Narrative goes here." in md

    def test_contains_metadata_section(self, builder):
        d = _debate_with_history()
        md = builder.assemble_report_markdown(d, d.synthesis, "nar", synthesiser="claude")
        assert "Debate metadata" in md
        assert "**Questions asked:**" in md

    def test_contains_question_and_synthesiser(self, builder):
        d = _debate_with_history()
        md = builder.assemble_report_markdown(d, d.synthesis, "nar", synthesiser="gemini")
        assert "Should we ship?" in md
        assert "Synthesised by:** Gemini" in md

    def test_contains_final_positions_section(self, builder):
        d = _debate_with_history()
        md = builder.assemble_report_markdown(d, d.synthesis, "nar", synthesiser="claude")
        assert "Final positions" in md
        # Each elder's last-round text is rendered.
        assert "C R3" in md
        assert "G R3" in md
        assert "X R3" in md

    def test_narrative_section_is_labelled_consensus_audit(self, builder):
        d = _debate_with_history()
        md = builder.assemble_report_markdown(d, d.synthesis, "nar", synthesiser="claude")
        assert "Narrative & consensus audit" in md

    def test_truncates_long_prompt_in_header_and_appends_source(self, builder):
        d = _debate_with_history()
        d = Debate(
            id=d.id,
            prompt=(
                "Short question here. Followed by a LOT of pasted source "
                "material that keeps going for many lines and is a mess."
                + ("\n\nmore lines\n" * 20)
            ),
            pack=d.pack,
            rounds=d.rounds,
            status=d.status,
            synthesis=d.synthesis,
        )
        md = builder.assemble_report_markdown(d, d.synthesis, "nar", synthesiser="claude")
        # Header only carries the first sentence.
        header_block = md.split("## Synthesised answer")[0]
        assert "Short question here." in header_block
        assert "more lines" not in header_block
        # Marker points the reader at the appendix.
        assert "full source material appears at the end" in header_block
        # Full text appears in the appendix.
        assert "## Full question (source material)" in md
        assert "more lines" in md

    def test_short_prompt_does_not_trigger_appendix(self, builder):
        d = _debate_with_history()  # prompt is "Should we ship?"
        md = builder.assemble_report_markdown(d, d.synthesis, "nar", synthesiser="claude")
        assert "## Full question (source material)" not in md

    def test_demotes_headings_in_synthesis_text(self, builder):
        import re

        d = _debate_with_history()
        # Synthesis with a heading would normally collide with the
        # enclosing `## Synthesised answer` section.
        bad_synth = d.synthesis.__class__(
            elder=d.synthesis.elder,
            text="## The answer\nDetails go here.",
            error=None,
            agreed=None,
            created_at=d.synthesis.created_at,
        )
        md = builder.assemble_report_markdown(d, bad_synth, "nar", synthesiser="claude")
        assert "#### The answer" in md
        # No `##`-level heading line starting "The answer" (demoted to ####).
        assert not re.search(r"^## The answer", md, flags=re.MULTILINE)


class TestDebateServiceGenerateReport:
    async def test_uses_synthesiser_elder_for_narrative(self):
        d = _debate_with_history()
        elders = {
            "claude": FakeElder(elder_id="claude", replies=["Narrative from Claude."]),
            "gemini": FakeElder(elder_id="gemini", replies=[]),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=[]),
        }
        svc = DebateService(
            elders=elders,
            store=InMemoryStore(),
            clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
            bus=InMemoryBus(),
        )
        md = await svc.generate_report(d, by="claude")
        assert "Narrative from Claude." in md
        # And the conversation passed to Claude ends with the narrative-request.
        convo = elders["claude"].conversations[-1]
        assert convo[-1].role == "user"
        low = convo[-1].content.lower()
        assert "analysis" in low or "debate" in low
        assert "consensus" in low

    async def test_raises_if_no_synthesis(self):
        d = _debate_with_history()
        d.synthesis = None
        svc = DebateService(
            elders={
                "claude": FakeElder(elder_id="claude", replies=[]),
                "gemini": FakeElder(elder_id="gemini", replies=[]),
                "chatgpt": FakeElder(elder_id="chatgpt", replies=[]),
            },
            store=InMemoryStore(),
            clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
            bus=InMemoryBus(),
        )
        with pytest.raises(ValueError):
            await svc.generate_report(d, by="claude")
