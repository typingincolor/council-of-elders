import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


from council.app.headless.reporting import (
    emit_openrouter_cost_notice,
    generate_and_save_report,
    judge_preference_verdict,
    run_synthesis,
    synthesis_risk_note,
    write_summary_sidecar,
)
from council.domain.debate_policy import DebatePolicy
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)
from council.domain.preference import (
    JudgeVerdict,
    MultiJudgeVerdict,
    PreferenceVerdict,
)
from council.domain.roster import RosterSpec
from council.domain.synthesis_output import SynthesisOutput


def _policy(*, mode="full_debate", synthesise=True, max_rounds=3):
    return DebatePolicy(
        mode=mode,
        max_rounds=max_rounds,
        synthesise=synthesise,
        always_compute_best_r1=True,
        warning=None,
    )


def _roster(models=None):
    return RosterSpec(name="t", models=models or {"ada": "a", "kai": "b", "mei": "c"})


def _ans(elder="ada", text="hi"):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def _debate():
    return Debate(
        id="debate-xyz",
        prompt="q",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[Round(number=1, turns=[Turn(elder="ada", answer=_ans())])],
        status="in_progress",
        synthesis=None,
    )


def _structured(answer="final"):
    return SynthesisOutput(answer=answer, why="", disagreements=(), raw=f"ANSWER:\n{answer}")


class TestSynthesisRiskNote:
    def test_none_when_policy_skips_synthesis(self):
        assert synthesis_risk_note(policy=_policy(synthesise=False), roster_spec=_roster()) is None

    def test_none_when_no_roster(self):
        assert synthesis_risk_note(policy=_policy(), roster_spec=None) is None

    def test_none_when_roster_has_no_models(self):
        assert (
            synthesis_risk_note(policy=_policy(), roster_spec=RosterSpec(name="t", models={}))
            is None
        )

    def test_note_on_low_diversity(self, monkeypatch):
        # Force classification by patching score_roster.
        from council.domain.diversity import DiversityScore

        monkeypatch.setattr(
            "council.app.headless.reporting.score_roster",
            lambda _r: DiversityScore(
                classification="low",
                provider_count=1,
                identical_model_count=0,
                flags=(),
                rationale="t",
            ),
        )
        note = synthesis_risk_note(policy=_policy(), roster_spec=_roster())
        assert note is not None
        assert "low-diversity" in note

    def test_note_on_medium_diversity(self, monkeypatch):
        from council.domain.diversity import DiversityScore

        monkeypatch.setattr(
            "council.app.headless.reporting.score_roster",
            lambda _r: DiversityScore(
                classification="medium",
                provider_count=2,
                identical_model_count=0,
                flags=(),
                rationale="t",
            ),
        )
        note = synthesis_risk_note(policy=_policy(), roster_spec=_roster())
        assert note is not None
        assert "medium-diversity" in note

    def test_omitted_on_high_diversity(self, monkeypatch):
        from council.domain.diversity import DiversityScore

        monkeypatch.setattr(
            "council.app.headless.reporting.score_roster",
            lambda _r: DiversityScore(
                classification="high",
                provider_count=3,
                identical_model_count=0,
                flags=(),
                rationale="t",
            ),
        )
        assert synthesis_risk_note(policy=_policy(), roster_spec=_roster()) is None


class TestRunSynthesis:
    async def test_returns_parsed_synthesis(self):
        svc = MagicMock()
        synth_answer = _ans("ada", "ANSWER:\nfinal body")
        svc.synthesize = AsyncMock(return_value=synth_answer)
        debate = _debate()

        result = await run_synthesis(svc=svc, debate=debate, synthesizer="ada")

        svc.synthesize.assert_awaited_once_with(debate, by="ada")
        assert result.answer == "final body"


class TestJudgePreferenceVerdict:
    async def test_multi_judge_path_takes_precedence(self, monkeypatch):
        async def _fake_multi(**kw):
            assert kw["question"] == "q"
            return MultiJudgeVerdict(verdicts=(), aggregate="synthesis", unanimous=True)

        async def _fake_single(**kw):
            raise AssertionError("single should not be called when multi provided")

        monkeypatch.setattr("council.app.headless.reporting.judge_preference_multi", _fake_multi)
        monkeypatch.setattr("council.app.headless.reporting.judge_preference", _fake_single)

        out = await judge_preference_verdict(
            prompt="q",
            synthesis_answer="s",
            best_r1_text="r",
            preference_judge=MagicMock(),  # would be ignored
            preference_judges=[("model-a", MagicMock())],
        )
        assert isinstance(out, MultiJudgeVerdict)

    async def test_falls_back_to_single_judge(self, monkeypatch):
        sentinel = PreferenceVerdict(winner="best_r1", reason="r", raw="")

        async def _fake_single(**kw):
            return sentinel

        monkeypatch.setattr("council.app.headless.reporting.judge_preference", _fake_single)

        out = await judge_preference_verdict(
            prompt="q",
            synthesis_answer="s",
            best_r1_text="r",
            preference_judge=MagicMock(),
            preference_judges=None,
        )
        assert out is sentinel

    async def test_returns_none_when_neither_configured(self):
        out = await judge_preference_verdict(
            prompt="q",
            synthesis_answer="s",
            best_r1_text="r",
            preference_judge=None,
            preference_judges=None,
        )
        assert out is None


class TestGenerateAndSaveReport:
    async def test_success_and_saves_when_store_present(self):
        svc = MagicMock()
        svc.generate_report = AsyncMock(return_value="# body")
        store = MagicMock()
        store.save.return_value = Path("/tmp/xyz.md")
        buf = io.StringIO()
        with redirect_stdout(buf):
            await generate_and_save_report(
                svc=svc,
                debate=_debate(),
                synthesizer="ada",
                risk_note=None,
                report_store=store,
            )
        assert svc.generate_report.await_count == 1
        store.save.assert_called_once()
        out = buf.getvalue()
        assert "# body" in out
        assert "Report saved to /tmp/xyz.md" in out

    async def test_success_without_store_skips_save(self):
        svc = MagicMock()
        svc.generate_report = AsyncMock(return_value="# body")
        buf = io.StringIO()
        with redirect_stdout(buf):
            await generate_and_save_report(
                svc=svc,
                debate=_debate(),
                synthesizer="ada",
                risk_note=None,
                report_store=None,
            )
        out = buf.getvalue()
        assert "# body" in out
        assert "Report saved to" not in out

    async def test_failure_is_caught_and_prints_warning(self):
        svc = MagicMock()
        svc.generate_report = AsyncMock(side_effect=RuntimeError("llm down"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            await generate_and_save_report(
                svc=svc,
                debate=_debate(),
                synthesizer="ada",
                risk_note=None,
                report_store=MagicMock(),
            )
        assert "Report generation failed: llm down" in buf.getvalue()

    async def test_passes_risk_note_to_generate_report(self):
        svc = MagicMock()
        svc.generate_report = AsyncMock(return_value="# body")
        await generate_and_save_report(
            svc=svc,
            debate=_debate(),
            synthesizer="ada",
            risk_note="[note] be careful",
            report_store=None,
        )
        kwargs = svc.generate_report.await_args.kwargs
        assert kwargs["synthesis_risk_note"] == "[note] be careful"


class TestWriteSummarySidecar:
    def test_captures_preference_judge_model_for_single(self, tmp_path: Path):
        debate = _debate()
        pref_judge = MagicMock()
        pref_judge.model = "google/gemini-2.5-flash"
        pref = PreferenceVerdict(winner="synthesis", reason="", raw="")

        buf = io.StringIO()
        with redirect_stdout(buf):
            write_summary_sidecar(
                debate=debate,
                roster_spec=_roster(),
                policy=_policy(),
                structured=_structured(),
                preference=pref,
                preference_judge=pref_judge,
                root=tmp_path,
            )
        # The summary was written somewhere under tmp_path — locate it
        # and assert the judge model carried through.
        files = list(tmp_path.rglob("*.json"))
        assert files, "expected a summary json to be written"
        payload = json.loads(files[0].read_text())
        # Provenance shows up under preference somewhere — scan the raw text.
        assert "google/gemini-2.5-flash" in files[0].read_text(), payload

    def test_multi_verdict_does_not_set_single_model_field(self, tmp_path: Path):
        debate = _debate()
        pref = MultiJudgeVerdict(
            verdicts=(
                JudgeVerdict(
                    judge_model="anthropic/claude-haiku-4.5",
                    verdict=PreferenceVerdict(winner="synthesis", reason="", raw=""),
                ),
            ),
            aggregate="synthesis",
            unanimous=True,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            write_summary_sidecar(
                debate=debate,
                roster_spec=_roster(),
                policy=_policy(),
                structured=_structured(),
                preference=pref,
                preference_judge=MagicMock(model="single-should-be-ignored"),
                root=tmp_path,
            )
        text = next(tmp_path.rglob("*.json")).read_text()
        assert "single-should-be-ignored" not in text
        assert "anthropic/claude-haiku-4.5" in text

    def test_prints_sidecar_path(self, tmp_path: Path):
        buf = io.StringIO()
        with redirect_stdout(buf):
            write_summary_sidecar(
                debate=_debate(),
                roster_spec=None,
                policy=_policy(),
                structured=None,
                preference=None,
                preference_judge=None,
                root=tmp_path,
            )
        assert "[run summary]" in buf.getvalue()


class TestEmitOpenRouterCostNotice:
    async def test_no_openrouter_adapters_prints_zero_delta_line(self):
        # elders dict with non-OpenRouter adapters → sum() over filtered
        # is 0, credits fetch is skipped, format_cost_notice is still called.
        from council.adapters.elders.fake import FakeElder

        elders = {"ada": FakeElder(elder_id="ada", replies=[])}
        buf = io.StringIO()
        with redirect_stdout(buf):
            await emit_openrouter_cost_notice(elders)
        # Only assertion: something was printed. The exact line shape
        # depends on format_cost_notice; we don't pin it here — we just
        # verify the helper doesn't crash on subprocess-only rosters.
        assert buf.getvalue() != ""
