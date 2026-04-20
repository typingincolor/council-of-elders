from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from council.domain.elder_migration import migrate_slot_id
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


@dataclass
class JsonFileStore:
    root: Path

    def save(self, debate: Debate) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{debate.id}.json"
        # Atomic write: stage to a sibling temp file, then rename into place.
        # os.replace is atomic on POSIX and Windows, so a crash mid-write leaves
        # the previous version intact rather than a truncated file.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(_serialize_debate(debate), indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, debate_id: str) -> Debate:
        path = self.root / f"{debate_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"No debate with id {debate_id} at {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return _deserialize_debate(data)


def _serialize_debate(d: Debate) -> dict[str, Any]:
    return {
        "id": d.id,
        "prompt": d.prompt,
        "pack": _serialize_pack(d.pack),
        "rounds": [_serialize_round(r) for r in d.rounds],
        "status": d.status,
        "synthesis": _serialize_answer(d.synthesis) if d.synthesis else None,
        "user_messages": [_serialize_user_message(m) for m in d.user_messages],
        "best_r1_elder": d.best_r1_elder,
    }


def _serialize_pack(p: CouncilPack) -> dict[str, Any]:
    return {
        "name": p.name,
        "shared_context": p.shared_context,
        "personas": dict(p.personas),
    }


def _serialize_user_message(m: UserMessage) -> dict[str, Any]:
    return {
        "text": m.text,
        "after_round": m.after_round,
        "created_at": m.created_at.isoformat(),
    }


def _serialize_round(r: Round) -> dict[str, Any]:
    return {
        "number": r.number,
        "turns": [
            {
                "elder": t.elder,
                "answer": _serialize_answer(t.answer),
                "questions": [_serialize_question(q) for q in t.questions],
            }
            for t in r.turns
        ],
    }


def _serialize_answer(a: ElderAnswer) -> dict[str, Any]:
    return {
        "elder": a.elder,
        "text": a.text,
        "error": (
            None
            if a.error is None
            else {"elder": a.error.elder, "kind": a.error.kind, "detail": a.error.detail}
        ),
        "agreed": a.agreed,
        "created_at": a.created_at.isoformat(),
    }


def _serialize_question(q: ElderQuestion) -> dict[str, Any]:
    return {
        "from_elder": q.from_elder,
        "to_elder": q.to_elder,
        "text": q.text,
        "round_number": q.round_number,
    }


def _migrated_slot(slot: str | None) -> str | None:
    return None if slot is None else migrate_slot_id(slot)


def _deserialize_debate(d: dict[str, Any]) -> Debate:
    debate = Debate(
        id=d["id"],
        prompt=d["prompt"],
        pack=_deserialize_pack(d["pack"]),
        rounds=[_deserialize_round(r) for r in d["rounds"]],
        status=d["status"],
        synthesis=_deserialize_answer(d["synthesis"]) if d["synthesis"] else None,
        best_r1_elder=_migrated_slot(d.get("best_r1_elder")),  # type: ignore[arg-type]
    )
    for m in d.get("user_messages", []):
        debate.user_messages.append(_deserialize_user_message(m))
    return debate


def _deserialize_pack(p: dict[str, Any]) -> CouncilPack:
    return CouncilPack(
        name=p["name"],
        shared_context=p["shared_context"],
        personas={migrate_slot_id(k): v for k, v in p["personas"].items()},
    )


def _deserialize_user_message(m: dict[str, Any]) -> UserMessage:
    return UserMessage(
        text=m["text"],
        after_round=m["after_round"],
        created_at=datetime.fromisoformat(m["created_at"]),
    )


def _deserialize_round(r: dict[str, Any]) -> Round:
    return Round(
        number=r["number"],
        turns=[
            Turn(
                elder=migrate_slot_id(t["elder"]),
                answer=_deserialize_answer(t["answer"]),
                questions=tuple(_deserialize_question(q) for q in t.get("questions", [])),
            )
            for t in r["turns"]
        ],
    )


def _deserialize_answer(a: dict[str, Any]) -> ElderAnswer:
    err = a["error"]
    return ElderAnswer(
        elder=migrate_slot_id(a["elder"]),
        text=a["text"],
        error=(
            None
            if err is None
            else ElderError(
                elder=migrate_slot_id(err["elder"]), kind=err["kind"], detail=err["detail"]
            )
        ),
        agreed=a["agreed"],
        created_at=datetime.fromisoformat(a["created_at"]),
    )


def _deserialize_question(q: dict[str, Any]) -> ElderQuestion:
    return ElderQuestion(
        from_elder=migrate_slot_id(q["from_elder"]),
        to_elder=migrate_slot_id(q["to_elder"]),
        text=q["text"],
        round_number=q["round_number"],
    )
