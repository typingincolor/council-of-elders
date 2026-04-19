from council.experiments.homogenisation.rosters import (
    ROSTERS,
    RosterSpec,
    build_roster_elders,
)


def test_rosters_are_named_correctly() -> None:
    names = {r.name for r in ROSTERS}
    assert names == {"homogeneous", "mixed_baseline", "substituted"}


def test_homogeneous_roster_uses_same_model_in_all_slots() -> None:
    hom = next(r for r in ROSTERS if r.name == "homogeneous")
    assert hom.models["claude"] == hom.models["gemini"] == hom.models["chatgpt"]


def test_substituted_roster_places_llama_in_gemini_slot() -> None:
    sub = next(r for r in ROSTERS if r.name == "substituted")
    assert "llama" in sub.models["gemini"].lower()
    assert "claude" in sub.models["claude"].lower()
    assert "openai" in sub.models["chatgpt"].lower()


def test_build_roster_elders_returns_openrouter_adapters() -> None:
    from council.adapters.elders.openrouter import OpenRouterAdapter

    spec = RosterSpec(
        name="test",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        },
    )
    elders = build_roster_elders(spec, api_key="sk-test")
    assert set(elders.keys()) == {"claude", "gemini", "chatgpt"}
    for slot in ("claude", "gemini", "chatgpt"):
        assert isinstance(elders[slot], OpenRouterAdapter)
        assert elders[slot].model == spec.models[slot]
        assert elders[slot].api_key == "sk-test"
        assert elders[slot].elder_id == slot
