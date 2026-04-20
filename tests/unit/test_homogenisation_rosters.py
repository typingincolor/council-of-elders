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
    assert hom.models["ada"] == hom.models["kai"] == hom.models["mei"]


def test_substituted_roster_places_llama_in_kai_slot() -> None:
    sub = next(r for r in ROSTERS if r.name == "substituted")
    assert "llama" in sub.models["kai"].lower()
    assert "anthropic" in sub.models["ada"].lower()
    assert "openai" in sub.models["mei"].lower()


def test_build_roster_elders_returns_openrouter_adapters() -> None:
    from council.adapters.elders.openrouter import OpenRouterAdapter

    spec = RosterSpec(
        name="test",
        models={
            "ada": "anthropic/claude-sonnet-4.5",
            "kai": "google/gemini-2.5-pro",
            "mei": "openai/gpt-5",
        },
    )
    elders = build_roster_elders(spec, api_key="sk-test")
    assert set(elders.keys()) == {"ada", "kai", "mei"}
    for slot in ("ada", "kai", "mei"):
        assert isinstance(elders[slot], OpenRouterAdapter)
        assert elders[slot].model == spec.models[slot]
        assert elders[slot].api_key == "sk-test"
        assert elders[slot].elder_id == slot
