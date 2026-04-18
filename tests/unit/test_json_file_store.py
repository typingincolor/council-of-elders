from datetime import datetime, timezone
from pathlib import Path
import pytest

from council.adapters.storage.json_file import JsonFileStore
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    Round,
    Turn,
)


def _round_with_all_elders() -> Round:
    t = datetime(2026, 4, 18, tzinfo=timezone.utc)
    return Round(
        number=1,
        turns=[
            Turn(
                elder="claude",
                answer=ElderAnswer(
                    elder="claude", text="ok", error=None, agreed=True, created_at=t
                ),
            ),
            Turn(
                elder="gemini",
                answer=ElderAnswer(
                    elder="gemini",
                    text=None,
                    error=ElderError(elder="gemini", kind="timeout", detail=""),
                    agreed=None,
                    created_at=t,
                ),
            ),
            Turn(
                elder="chatgpt",
                answer=ElderAnswer(
                    elder="chatgpt",
                    text="maybe",
                    error=None,
                    agreed=False,
                    created_at=t,
                ),
            ),
        ],
    )


def _debate() -> Debate:
    return Debate(
        id="d1",
        prompt="What should I do?",
        pack=CouncilPack(name="coo", shared_context="help", personas={"claude": "legal"}),
        rounds=[_round_with_all_elders()],
        status="in_progress",
        synthesis=None,
    )


def test_save_then_load_round_trips(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    original = _debate()
    store.save(original)
    loaded = store.load("d1")
    assert loaded.id == "d1"
    assert loaded.prompt == original.prompt
    assert loaded.pack.shared_context == "help"
    assert loaded.pack.personas == {"claude": "legal"}
    assert len(loaded.rounds) == 1
    assert {t.elder for t in loaded.rounds[0].turns} == {"claude", "gemini", "chatgpt"}
    gem = next(t for t in loaded.rounds[0].turns if t.elder == "gemini")
    assert gem.answer.error is not None
    assert gem.answer.error.kind == "timeout"


def test_load_missing_raises(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("nope")


def test_save_overwrites_existing(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    original = _debate()
    store.save(original)
    original.status = "abandoned"
    store.save(original)
    loaded = store.load("d1")
    assert loaded.status == "abandoned"
