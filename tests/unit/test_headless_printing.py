import io
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from council.app.headless.printing import (
    print_best_r1_only_deliverable,
    print_best_r1_pick,
    print_best_r1_unavailable,
    print_max_rounds_exhausted,
    print_policy_warning,
    print_preference,
    print_report,
    print_report_failed,
    print_rounds,
    print_run_summary_path,
    print_synthesis,
)
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    Round,
    Turn,
)
from council.domain.preference import JudgeVerdict, MultiJudgeVerdict, PreferenceVerdict
from council.domain.synthesis_output import SynthesisOutput


def _capture(fn, *args, **kwargs) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def _ans(elder, text, *, error=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=error,
        agreed=None,
        created_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def _debate_with_rounds(*rounds) -> Debate:
    return Debate(
        id="t",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=list(rounds),
        status="in_progress",
        synthesis=None,
    )


class TestPrintRounds:
    def test_emits_real_newlines_not_literal_backslash_n(self):
        # Regression guard for PR 15: the extraction accidentally wrote
        # "\\n" in the f-strings, emitting the literal two-character
        # sequence instead of a newline. This check fails if that ever
        # recurs.
        debate = _debate_with_rounds(
            Round(number=1, turns=[Turn(elder="ada", answer=_ans("ada", "hi"))]),
        )
        out = _capture(print_rounds, debate)
        # Strip all real newlines; any remaining "\n" is the literal bug.
        assert "\\n" not in out.replace("\n", "")

    def test_prints_round_header_and_labels(self):
        debate = _debate_with_rounds(
            Round(
                number=2,
                turns=[
                    Turn(elder="ada", answer=_ans("ada", "alpha")),
                    Turn(elder="kai", answer=_ans("kai", "beta")),
                ],
            ),
        )
        out = _capture(print_rounds, debate)
        assert "--- Round 2 ---" in out
        assert "[Ada] alpha" in out
        assert "[Kai] beta" in out

    def test_formats_error_turn(self):
        err = ElderError(elder="mei", kind="timeout", detail="slow")
        debate = _debate_with_rounds(
            Round(
                number=1,
                turns=[Turn(elder="mei", answer=_ans("mei", "", error=err))],
            ),
        )
        out = _capture(print_rounds, debate)
        assert "[Mei] ERROR timeout: slow" in out

    def test_uses_elder_label_not_raw_id(self):
        debate = _debate_with_rounds(
            Round(number=1, turns=[Turn(elder="kai", answer=_ans("kai", "x"))]),
        )
        out = _capture(print_rounds, debate)
        assert "[Kai]" in out
        assert "[kai]" not in out


class TestPrintBestR1:
    def test_pick_uses_label(self):
        out = _capture(print_best_r1_pick, "kai", "clearest")
        assert "Best R1 (judge-picked): Kai" in out
        assert "clearest" in out

    def test_unavailable_message(self):
        out = _capture(print_best_r1_unavailable)
        assert "Best-R1 baseline unavailable" in out


class TestPrintSynthesis:
    def _structured(self, *, why="", disagreements=()):
        return SynthesisOutput(
            answer="final answer",
            why=why,
            disagreements=disagreements,
            raw="ANSWER:\nfinal answer",
        )

    def test_shows_header_and_body(self):
        out = _capture(
            print_synthesis,
            structured=self._structured(),
            synthesizer="ada",
            risk_note=None,
        )
        assert "[Synthesis by Ada]" in out
        assert "final answer" in out

    def test_shows_risk_note_when_provided(self):
        out = _capture(
            print_synthesis,
            structured=self._structured(),
            synthesizer="ada",
            risk_note="[note] careful now",
        )
        assert "[note] careful now" in out

    def test_omits_why_when_empty(self):
        out = _capture(
            print_synthesis,
            structured=self._structured(why=""),
            synthesizer="ada",
            risk_note=None,
        )
        assert "Why:" not in out

    def test_prints_why_when_present(self):
        out = _capture(
            print_synthesis,
            structured=self._structured(why="because reasons"),
            synthesizer="ada",
            risk_note=None,
        )
        assert "Why: because reasons" in out

    def test_none_material_when_no_disagreements(self):
        out = _capture(
            print_synthesis,
            structured=self._structured(disagreements=()),
            synthesizer="ada",
            risk_note=None,
        )
        assert "Disagreements: none material." in out

    def test_lists_disagreements_when_present(self):
        out = _capture(
            print_synthesis,
            structured=self._structured(disagreements=("alpha", "beta")),
            synthesizer="ada",
            risk_note=None,
        )
        assert "- alpha" in out
        assert "- beta" in out


class TestPrintPreference:
    def test_single_verdict_formats_winner(self):
        v = PreferenceVerdict(winner="synthesis", reason="it's tighter", raw="")
        out = _capture(print_preference, v)
        assert "[Preference judge]" in out
        assert "synthesis — it's tighter" in out

    def test_multi_lists_aggregate_and_per_judge(self):
        per = (
            JudgeVerdict(
                judge_model="google/gemini-2.5-flash",
                verdict=PreferenceVerdict(winner="best_r1", reason="r1 concrete", raw=""),
            ),
            JudgeVerdict(
                judge_model="anthropic/claude-haiku-4.5",
                verdict=PreferenceVerdict(winner="synthesis", reason="synth fuller", raw=""),
            ),
        )
        mv = MultiJudgeVerdict(verdicts=per, aggregate="tie", unanimous=False)
        out = _capture(print_preference, mv)
        assert "aggregate=tie" in out
        assert "unanimous=False" in out
        assert "n_judges=2" in out
        assert "google/gemini-2.5-flash: best_r1 — r1 concrete" in out
        assert "anthropic/claude-haiku-4.5: synthesis — synth fuller" in out


class TestPrintReport:
    def test_without_save_path_omits_saved_line(self):
        out = _capture(print_report, "# report body", saved_to=None)
        assert "--- Debate report ---" in out
        assert "# report body" in out
        assert "Report saved to" not in out

    def test_with_save_path_shows_saved_line(self):
        out = _capture(print_report, "# report", saved_to=Path("/tmp/x.md"))
        assert "Report saved to /tmp/x.md" in out


class TestPrintBestR1OnlyDeliverable:
    def test_prints_answer_when_elder_and_text_present(self):
        debate = _debate_with_rounds()
        debate.best_r1_elder = "kai"
        out = _capture(print_best_r1_only_deliverable, debate, "the answer")
        assert "[Answer (best-R1, Kai)] the answer" in out

    def test_warns_when_no_elder(self):
        debate = _debate_with_rounds()
        out = _capture(print_best_r1_only_deliverable, debate, None)
        assert "[warning] best-R1-only mode but no judge available" in out

    def test_warns_when_no_text(self):
        debate = _debate_with_rounds()
        debate.best_r1_elder = "mei"
        out = _capture(print_best_r1_only_deliverable, debate, None)
        assert "[warning]" in out


class TestMiscPrints:
    def test_run_summary_path(self):
        out = _capture(print_run_summary_path, Path("/tmp/sum.json"))
        assert "[run summary] /tmp/sum.json" in out

    def test_policy_warning(self):
        out = _capture(print_policy_warning, "homogeneous roster")
        assert "[warning] homogeneous roster" in out

    def test_max_rounds_exhausted(self):
        out = _capture(print_max_rounds_exhausted, 6)
        assert "[warning] Hit policy max_rounds=6" in out
        assert "Synthesising best-effort" in out

    def test_report_failed(self):
        out = _capture(print_report_failed, RuntimeError("boom"))
        assert "[warning] Report generation failed: boom" in out
