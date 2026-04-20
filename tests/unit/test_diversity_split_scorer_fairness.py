"""Regression test for the 2026-04-20 scoring-fairness bug.

The preference judge used to receive the raw synthesis text including
``ANSWER:``/``WHY:``/``DISAGREEMENTS:`` structural labels. Those labels
never appear in the user-facing deliverable (``run_headless`` parses
the raw text with ``parse_synthesis`` before printing only the ANSWER
body). Sending the raw text to a judge whose rubric explicitly
penalises "bloat" and "shape-fit" systematically handicapped synthesis.

This test asserts that the scorer extracts the ANSWER section before
sending to the preference judge. Implementation: capture the judge's
conversation history via ``FakeElder`` and inspect the prompt.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from council.adapters.elders.fake import FakeElder
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)
from council.experiments.diversity_split.scorer import _score_one_debate


def _ans(elder: str, text: str) -> ElderAnswer:
    return ElderAnswer(
        elder=elder,  # type: ignore[arg-type]
        text=text,
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


def _debate_with_structured_synthesis() -> Debate:
    r1 = Round(
        number=1,
        turns=[
            Turn(elder="ada", answer=_ans("ada", "Ada R1 answer — clean prose.")),
            Turn(elder="kai", answer=_ans("kai", "Kai R1 answer — clean prose.")),
            Turn(elder="mei", answer=_ans("mei", "Mei R1 answer — clean prose.")),
        ],
    )
    structured_synthesis_text = (
        "ANSWER:\nThe final answer body is this clean sentence.\n\n"
        "WHY:\nShort rationale the user didn't ask for.\n\n"
        "DISAGREEMENTS:\n- A point of divergence.\n- Another point.\n"
    )
    return Debate(
        id="fixture",
        prompt="Test question?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[r1],
        status="synthesized",
        synthesis=_ans("ada", structured_synthesis_text),
    )


async def test_preference_judge_receives_parsed_answer_not_raw_text():
    """The preference judge prompt must contain the ANSWER body, and
    must NOT contain the structural labels or the WHY/DISAGREEMENTS
    sections. Regression guard for the 2026-04-20 scoring bug.
    """
    single_judge = FakeElder(
        elder_id="ada",
        replies=[
            # 3 pairwise claim-overlap responses
            "shared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n",
            "shared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n",
            "shared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n",
            # best-R1 pick
            "best: 1\nreason: clearest.\n",
        ],
    )
    preference_judge = FakeElder(
        elder_id="ada",
        replies=["winner: X\nreason: arbitrary.\n"],
    )

    await _score_one_debate(
        _debate_with_structured_synthesis(),
        single_judge=single_judge,
        preference_judges=[("fake/judge", preference_judge)],
        rng=random.Random(0),
    )

    # Inspect the last conversation the preference judge saw.
    assert len(preference_judge.conversations) == 1
    conv = preference_judge.conversations[0]
    # conv is list[Message]; the prompt is the user message content.
    prompt_text = conv[0].content

    # MUST contain the parsed ANSWER body.
    assert "The final answer body is this clean sentence." in prompt_text

    # MUST NOT contain the structural labels or the sections below ANSWER.
    assert "ANSWER:" not in prompt_text
    assert "WHY:" not in prompt_text
    assert "DISAGREEMENTS:" not in prompt_text
    assert "Short rationale the user didn't ask for." not in prompt_text
    assert "A point of divergence." not in prompt_text


async def test_preference_judge_handles_unstructured_synthesis():
    """Synthesiser didn't emit the structure → parser's fallback path
    returns the whole text as the answer. Scorer should still send
    exactly that to the judge, unwrapped.
    """
    single_judge = FakeElder(
        elder_id="ada",
        replies=[
            "shared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n",
            "shared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n",
            "shared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n",
            "best: 1\nreason: clearest.\n",
        ],
    )
    preference_judge = FakeElder(
        elder_id="ada",
        replies=["winner: X\nreason: arbitrary.\n"],
    )

    debate = _debate_with_structured_synthesis()
    # Replace synthesis with unstructured text.
    debate.synthesis = _ans("ada", "Just a plain answer, no labels at all.")

    await _score_one_debate(
        debate,
        single_judge=single_judge,
        preference_judges=[("fake/judge", preference_judge)],
        rng=random.Random(0),
    )

    conv = preference_judge.conversations[0]
    prompt_text = conv[0].content
    assert "Just a plain answer, no labels at all." in prompt_text
