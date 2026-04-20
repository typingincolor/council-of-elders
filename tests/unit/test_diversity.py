from council.domain.diversity import DiversityScore, provider_of, score_roster
from council.domain.roster import RosterSpec


def _spec(**models):
    return RosterSpec(name="t", models=models)


class TestProviderOf:
    def test_anthropic_prefix(self):
        assert provider_of("anthropic/claude-sonnet-4.5") == "anthropic"

    def test_openai_prefix(self):
        assert provider_of("openai/gpt-5") == "openai"

    def test_google_prefix(self):
        assert provider_of("google/gemini-2.5-pro") == "google"

    def test_meta_prefix(self):
        assert provider_of("meta-llama/llama-3.1-70b-instruct") == "meta-llama"

    def test_unknown_prefix_returns_prefix_verbatim(self):
        assert provider_of("novaco/frontier-2") == "novaco"

    def test_bare_model_id_returns_unknown(self):
        assert provider_of("sonnet") == "unknown"


class TestScoreRoster:
    def test_three_distinct_providers_no_identical_is_high(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="google/gemini-2.5-pro",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "high"
        assert s.provider_count == 3
        assert s.identical_model_count == 0
        assert s.flags == ()

    def test_open_weights_substitute_is_high(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="meta-llama/llama-3.1-70b-instruct",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "high"

    def test_all_three_identical_models_is_low(self):
        spec = _spec(
            claude="openai/gpt-5-mini",
            gemini="openai/gpt-5-mini",
            chatgpt="openai/gpt-5-mini",
        )
        s = score_roster(spec)
        assert s.classification == "low"
        assert "identical_models" in s.flags
        assert "same_provider_trio" in s.flags
        assert "unsafe_consensus_risk" in s.flags

    def test_same_provider_different_scale_is_low(self):
        # All three from anthropic — per the user's decision on question 15,
        # same provider/different scale was stated as "medium" conceptually,
        # but our tier-1 heuristic uses provider distinctness. Three
        # anthropic models = one provider = low. Document the gap rather
        # than pretend otherwise; tier-2 empirical diversity will fix this.
        spec = _spec(
            claude="anthropic/claude-opus-4.5",
            gemini="anthropic/claude-haiku-4.5",
            chatgpt="anthropic/claude-sonnet-4.5",
        )
        s = score_roster(spec)
        assert s.classification == "low"
        assert "same_provider_trio" in s.flags

    def test_two_providers_no_identical_is_medium(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="anthropic/claude-haiku-4.5",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        assert s.classification == "medium"

    def test_three_providers_but_two_identical_strings_is_medium(self):
        spec = _spec(
            claude="anthropic/claude-sonnet-4.5",
            gemini="anthropic/claude-sonnet-4.5",
            chatgpt="openai/gpt-5",
        )
        s = score_roster(spec)
        # Two distinct providers (anthropic duped) → medium by provider_count.
        assert s.classification == "medium"
        assert "identical_models" in s.flags

    def test_rationale_is_non_empty(self):
        s = score_roster(
            _spec(
                claude="openai/gpt-5-mini",
                gemini="openai/gpt-5-mini",
                chatgpt="openai/gpt-5-mini",
            )
        )
        assert s.rationale

    def test_diversity_score_is_frozen(self):
        import dataclasses
        import pytest

        s = DiversityScore(
            classification="high", provider_count=3, identical_model_count=0,
            flags=(), rationale="ok",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.classification = "low"  # type: ignore[misc]
