import json
from datetime import datetime, timezone
from pathlib import Path

from council.domain.debate_policy import DebatePolicy
from council.domain.diversity import DiversityScore
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)
from council.domain.preference import PreferenceVerdict
from council.domain.roster import RosterSpec
from council.domain.run_summary import build_run_summary, write_run_summary
from council.domain.synthesis_output import SynthesisOutput


def _ans(elder, text="x"):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


def _debate_with_one_round(best_r1: str | None = "kai"):
    r1 = Round(
        number=1,
        turns=[
            Turn(elder="ada", answer=_ans("ada", "c")),
            Turn(elder="kai", answer=_ans("kai", "g")),
            Turn(elder="mei", answer=_ans("mei", "x")),
        ],
    )
    return Debate(
        id="debate-xyz",
        prompt="What should I do?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[r1],
        status="synthesized",
        synthesis=_ans("ada", "ANSWER:\nShip.\n\nWHY:\nok.\n\nDISAGREEMENTS:\n(none)\n"),
        best_r1_elder=best_r1,  # type: ignore[arg-type]
    )


_HIGH_DIVERSITY = DiversityScore(
    classification="high",
    provider_count=3,
    identical_model_count=0,
    flags=(),
    rationale="three distinct providers",
)

_FULL_POLICY = DebatePolicy(
    mode="full_debate",
    max_rounds=6,
    synthesise=True,
    always_compute_best_r1=True,
    warning=None,
)

_ROSTER = RosterSpec(
    name="openrouter",
    models={
        "ada": "anthropic/claude-sonnet-4.5",
        "kai": "meta-llama/llama-3.1-70b-instruct",
        "mei": "openai/gpt-5",
    },
)


class TestBuildRunSummary:
    def test_captures_all_inputs(self):
        synth = SynthesisOutput(
            answer="Ship.",
            why="ok.",
            disagreements=(),
            raw="",
        )
        pref = PreferenceVerdict(winner="synthesis", reason="clearer", raw="")
        s = build_run_summary(
            debate=_debate_with_one_round(),
            roster_spec=_ROSTER,
            diversity=_HIGH_DIVERSITY,
            policy=_FULL_POLICY,
            synthesis=synth,
            preference=pref,
        )
        assert s.debate_id == "debate-xyz"
        assert s.prompt == "What should I do?"
        assert s.roster["name"] == "openrouter"
        assert s.roster["models"]["kai"] == "meta-llama/llama-3.1-70b-instruct"
        assert s.diversity["classification"] == "high"
        assert s.policy["mode"] == "full_debate"
        assert s.rounds_executed == 1
        assert s.best_r1_elder == "kai"
        assert s.synthesis_generated is True
        assert s.synthesis_structured == {
            "answer": "Ship.",
            "why": "ok.",
            "disagreements": [],
        }
        assert s.preference == {"winner": "synthesis", "reason": "clearer"}

    def test_handles_missing_synthesis_and_preference(self):
        s = build_run_summary(
            debate=_debate_with_one_round(best_r1=None),
            roster_spec=_ROSTER,
            diversity=_HIGH_DIVERSITY,
            policy=_FULL_POLICY,
            synthesis=None,
            preference=None,
        )
        assert s.best_r1_elder is None
        assert s.synthesis_generated is False
        assert s.synthesis_structured is None
        assert s.preference is None

    def test_handles_missing_roster_spec(self):
        s = build_run_summary(
            debate=_debate_with_one_round(),
            roster_spec=None,
            diversity=None,
            policy=_FULL_POLICY,
            synthesis=None,
            preference=None,
        )
        assert s.roster == {"name": "unknown", "models": {}}
        assert s.diversity["classification"] == "unknown"


class TestWriteRunSummary:
    def test_writes_json_file_with_expected_name(self, tmp_path: Path):
        s = build_run_summary(
            debate=_debate_with_one_round(),
            roster_spec=_ROSTER,
            diversity=_HIGH_DIVERSITY,
            policy=_FULL_POLICY,
            synthesis=None,
            preference=None,
        )
        path = write_run_summary(s, root=tmp_path)
        assert path == tmp_path / "debate-xyz-summary.json"
        assert path.exists()

    def test_roundtrip_through_json_is_stable(self, tmp_path: Path):
        s = build_run_summary(
            debate=_debate_with_one_round(),
            roster_spec=_ROSTER,
            diversity=_HIGH_DIVERSITY,
            policy=_FULL_POLICY,
            synthesis=SynthesisOutput(
                answer="Ship.",
                why="ok.",
                disagreements=("one minor point",),
                raw="",
            ),
            preference=PreferenceVerdict(winner="best_r1", reason="less bloat.", raw=""),
        )
        path = write_run_summary(s, root=tmp_path)
        data = json.loads(path.read_text())
        assert data["debate_id"] == "debate-xyz"
        assert data["diversity"]["classification"] == "high"
        assert data["policy"]["mode"] == "full_debate"
        assert data["preference"]["winner"] == "best_r1"
        assert data["synthesis_structured"]["disagreements"] == ["one minor point"]
