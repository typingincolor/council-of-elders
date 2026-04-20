from datetime import datetime, timezone
from pathlib import Path
import pytest

from council.adapters.storage.json_file import JsonFileStore
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    ElderQuestion,
    Round,
    Turn,
    UserMessage,
)


def _round_with_all_elders() -> Round:
    t = datetime(2026, 4, 18, tzinfo=timezone.utc)
    return Round(
        number=1,
        turns=[
            Turn(
                elder="ada",
                answer=ElderAnswer(elder="ada", text="ok", error=None, agreed=True, created_at=t),
            ),
            Turn(
                elder="kai",
                answer=ElderAnswer(
                    elder="kai",
                    text=None,
                    error=ElderError(elder="kai", kind="timeout", detail=""),
                    agreed=None,
                    created_at=t,
                ),
            ),
            Turn(
                elder="mei",
                answer=ElderAnswer(
                    elder="mei",
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
        pack=CouncilPack(name="coo", shared_context="help", personas={"ada": "legal"}),
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
    assert loaded.pack.personas == {"ada": "legal"}
    assert len(loaded.rounds) == 1
    assert {t.elder for t in loaded.rounds[0].turns} == {"ada", "kai", "mei"}
    gem = next(t for t in loaded.rounds[0].turns if t.elder == "kai")
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


def test_round_trips_user_messages(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    t = datetime(2026, 4, 19, tzinfo=timezone.utc)
    d = _debate()
    d.user_messages.append(UserMessage(text="clarify?", after_round=1, created_at=t))
    d.user_messages.append(UserMessage(text="follow up", after_round=2, created_at=t))
    store.save(d)
    loaded = store.load("d1")
    assert len(loaded.user_messages) == 2
    assert loaded.user_messages[0].text == "clarify?"
    assert loaded.user_messages[1].after_round == 2


def test_round_trips_turn_questions(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    t = datetime(2026, 4, 19, tzinfo=timezone.utc)
    d = _debate()
    q = ElderQuestion(from_elder="ada", to_elder="kai", text="timeline?", round_number=1)
    d.rounds[0].turns = [
        Turn(
            elder="ada",
            answer=ElderAnswer(elder="ada", text="ok", error=None, agreed=True, created_at=t),
            questions=(q,),
        ),
        Turn(
            elder="kai",
            answer=ElderAnswer(elder="kai", text="yes", error=None, agreed=True, created_at=t),
        ),
        Turn(
            elder="mei",
            answer=ElderAnswer(elder="mei", text="ok", error=None, agreed=True, created_at=t),
        ),
    ]
    store.save(d)
    loaded = store.load("d1")
    claude_turn = next(t_ for t_ in loaded.rounds[0].turns if t_.elder == "ada")
    assert len(claude_turn.questions) == 1
    assert claude_turn.questions[0].to_elder == "kai"
    assert claude_turn.questions[0].text == "timeline?"


def test_load_legacy_debate_without_user_messages_key(tmp_path: Path):
    # Simulate a pre-v3 file without the new keys.
    path = tmp_path / "d1.json"
    path.write_text(
        '{"id":"d1","prompt":"?",'
        '"pack":{"name":"b","shared_context":null,"personas":{}},'
        '"rounds":[],"status":"in_progress","synthesis":null}',
        encoding="utf-8",
    )
    store = JsonFileStore(root=tmp_path)
    loaded = store.load("d1")
    assert loaded.user_messages == []
    assert loaded.best_r1_elder is None


def test_round_trips_best_r1_elder(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    d = _debate()
    d.best_r1_elder = "kai"
    store.save(d)
    loaded = store.load("d1")
    assert loaded.best_r1_elder == "kai"
