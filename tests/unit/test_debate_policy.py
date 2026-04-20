import dataclasses

import pytest

from council.domain.debate_policy import DebatePolicy, policy_for
from council.domain.diversity import DiversityScore


def _score(cls, flags=()):
    return DiversityScore(
        classification=cls,
        provider_count=3 if cls == "high" else 1,
        identical_model_count=0,
        flags=flags,
        rationale="test rationale",
    )


class TestPolicyFor:
    def test_low_diversity_picks_best_r1_only(self):
        p = policy_for(_score("low", ("unsafe_consensus_risk",)))
        assert p.mode == "best_r1_only"
        assert p.max_rounds == 1
        assert p.synthesise is False
        assert p.always_compute_best_r1 is True
        assert p.warning is not None
        assert "low-diversity" in p.warning.lower()

    def test_medium_diversity_picks_single_critique(self):
        p = policy_for(_score("medium"))
        assert p.mode == "single_critique"
        assert p.max_rounds == 2
        assert p.synthesise is True
        assert p.always_compute_best_r1 is True
        assert p.warning is None

    def test_high_diversity_picks_full_debate(self):
        p = policy_for(_score("high"))
        assert p.mode == "full_debate"
        assert p.max_rounds >= 3
        assert p.synthesise is True
        assert p.always_compute_best_r1 is True
        assert p.warning is None

    def test_user_override_wins_over_diversity(self):
        override = DebatePolicy(
            mode="full_debate",
            max_rounds=6,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
        p = policy_for(_score("low"), user_override=override)
        assert p is override

    def test_debate_policy_is_frozen(self):
        p = policy_for(_score("high"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.mode = "single_critique"  # type: ignore[misc]
