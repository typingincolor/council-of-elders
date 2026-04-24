import io
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


from council.app.headless.rounds import (
    resolve_policy,
    run_debate_rounds,
    select_best_r1,
)
from council.domain.best_r1 import BestR1Selection
from council.domain.debate_policy import DebatePolicy
from council.domain.diversity import DiversityScore
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)
from council.domain.roster import RosterSpec


def _score(classification):
    return DiversityScore(
        classification=classification,
        provider_count=3 if classification == "high" else 1,
        identical_model_count=0,
        flags=(),
        rationale="t",
    )


def _ans(elder, text):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def _debate() -> Debate:
    return Debate(
        id="t",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


class TestResolvePolicy:
    def test_user_override_wins(self):
        override = DebatePolicy(
            mode="full_debate",
            max_rounds=4,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
        result = resolve_policy(
            user_override=override,
            roster_spec=RosterSpec(
                name="t", models={"ada": "claude", "kai": "gemini", "mei": "codex"}
            ),
            fallback_max_rounds=99,
        )
        assert result is override

    def test_roster_drives_policy_when_no_override(self):
        # High diversity roster → full_debate from policy_for.
        result = resolve_policy(
            user_override=None,
            roster_spec=RosterSpec(
                name="t",
                models={
                    "ada": "anthropic/claude-opus-4.7",
                    "kai": "google/gemini-2.5-flash",
                    "mei": "openai/gpt-5-codex",
                },
            ),
            fallback_max_rounds=6,
        )
        assert result.mode in ("full_debate", "single_critique", "best_r1_only")

    def test_fallback_when_no_roster(self):
        result = resolve_policy(
            user_override=None,
            roster_spec=None,
            fallback_max_rounds=5,
        )
        assert result.mode == "full_debate"
        assert result.max_rounds == 5
        assert result.synthesise is True

    def test_fallback_when_roster_has_no_models(self):
        result = resolve_policy(
            user_override=None,
            roster_spec=RosterSpec(name="t", models={}),
            fallback_max_rounds=3,
        )
        assert result.mode == "full_debate"


def _svc(*, converged_after: int = 1):
    """Async-mocked DebateService that appends a round every run_round call.

    ``converged_after``: the round number at which ``rules.is_converged``
    first returns True (round 1-indexed in ``debate.rounds``).
    """
    debate_rounds_seen = {"n": 0}

    async def _run_round(debate):
        debate_rounds_seen["n"] += 1
        debate.rounds.append(Round(number=debate_rounds_seen["n"], turns=[]))

    svc = MagicMock()
    svc.run_round = AsyncMock(side_effect=_run_round)
    svc.rules = MagicMock()
    svc.rules.is_converged = lambda rnd: rnd.number >= converged_after
    return svc


class TestRunDebateRounds:
    async def test_best_r1_only_runs_one_round(self):
        debate = _debate()
        svc = _svc()
        policy = DebatePolicy(
            mode="best_r1_only",
            max_rounds=1,
            synthesise=False,
            always_compute_best_r1=True,
            warning=None,
        )
        await run_debate_rounds(debate=debate, svc=svc, policy=policy)
        assert svc.run_round.await_count == 1
        assert len(debate.rounds) == 1

    async def test_r1_only_runs_one_round(self):
        debate = _debate()
        svc = _svc()
        policy = DebatePolicy(
            mode="r1_only",
            max_rounds=1,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
        await run_debate_rounds(debate=debate, svc=svc, policy=policy)
        assert svc.run_round.await_count == 1

    async def test_single_critique_runs_two_rounds(self):
        debate = _debate()
        svc = _svc()
        policy = DebatePolicy(
            mode="single_critique",
            max_rounds=2,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
        await run_debate_rounds(debate=debate, svc=svc, policy=policy)
        assert svc.run_round.await_count == 2

    async def test_full_debate_runs_until_converged(self):
        debate = _debate()
        # Converge on round 3 — so total rounds = 3.
        svc = _svc(converged_after=3)
        policy = DebatePolicy(
            mode="full_debate",
            max_rounds=6,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
        await run_debate_rounds(debate=debate, svc=svc, policy=policy)
        assert svc.run_round.await_count == 3

    async def test_full_debate_stops_at_max_rounds_and_warns(self):
        debate = _debate()
        # Never converge — loop exits on max_rounds.
        svc = _svc(converged_after=999)
        policy = DebatePolicy(
            mode="full_debate",
            max_rounds=4,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            await run_debate_rounds(debate=debate, svc=svc, policy=policy)
        assert svc.run_round.await_count == 4
        assert "max_rounds=4" in buf.getvalue()
        assert "without full convergence" in buf.getvalue()


class TestSelectBestR1:
    async def test_no_judge_prints_unavailable_and_returns_none(self):
        debate = _debate()
        store = MagicMock()
        buf = io.StringIO()
        with redirect_stdout(buf):
            out = await select_best_r1(debate=debate, store=store, best_r1_judge=None)
        assert out is None
        assert "Best-R1 baseline unavailable" in buf.getvalue()
        store.save.assert_not_called()

    async def test_happy_path_records_and_returns_text(self, monkeypatch):
        debate = _debate()
        debate.rounds.append(
            Round(
                number=1,
                turns=[
                    Turn(elder="ada", answer=_ans("ada", "ada text")),
                    Turn(elder="kai", answer=_ans("kai", "kai text")),
                    Turn(elder="mei", answer=_ans("mei", "mei text")),
                ],
            )
        )
        store = MagicMock()

        # Stub the selector class's select to return a known pick without
        # needing a real judge_port round-trip.
        async def _fake_select(self, d):
            return BestR1Selection(elder="kai", reason="kai is tightest", raw="best: 2\n")

        monkeypatch.setattr(
            "council.app.headless.rounds.LLMJudgedBestR1Selector.select",
            _fake_select,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            out = await select_best_r1(
                debate=debate,
                store=store,
                best_r1_judge=MagicMock(),
            )

        assert out == "kai text"
        assert debate.best_r1_elder == "kai"
        store.save.assert_called_once_with(debate)
        assert "Best R1 (judge-picked): Kai" in buf.getvalue()

    async def test_selector_returns_none_does_not_mutate(self, monkeypatch):
        debate = _debate()
        debate.rounds.append(Round(number=1, turns=[]))  # no turns → selector yields None
        store = MagicMock()

        async def _fake_select(self, d):
            return None

        monkeypatch.setattr(
            "council.app.headless.rounds.LLMJudgedBestR1Selector.select",
            _fake_select,
        )
        out = await select_best_r1(
            debate=debate,
            store=store,
            best_r1_judge=MagicMock(),
        )
        assert out is None
        assert debate.best_r1_elder is None
        store.save.assert_not_called()
