import dataclasses

import pytest

from council.domain.roster import RosterSpec


def test_roster_spec_holds_name_and_models():
    spec = RosterSpec(
        name="mixed",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        },
    )
    assert spec.name == "mixed"
    assert spec.models["claude"] == "anthropic/claude-sonnet-4.5"


def test_roster_spec_is_frozen():
    spec = RosterSpec(name="n", models={"claude": "m"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "other"  # type: ignore[misc]
