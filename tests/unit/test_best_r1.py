from datetime import datetime, timezone

import pytest

from council.adapters.elders.fake import FakeElder
from council.domain.best_r1 import BestR1Selection, LLMJudgedBestR1Selector
from council.domain.models import CouncilPack, Debate, ElderAnswer, Round, Turn


def _ans(elder, text):
    return ElderAnswer(
        elder=elder, text=text, error=None, agreed=None,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


def _debate_with_r1(
    claude_text: str = "Claude R1 answer.",
    gemini_text: str = "Gemini R1 answer.",
    chatgpt_text: str = "ChatGPT R1 answer.",
):
    r1 = Round(
        number=1,
        turns=[
            Turn(elder="claude", answer=_ans("claude", claude_text)),
            Turn(elder="gemini", answer=_ans("gemini", gemini_text)),
            Turn(elder="chatgpt", answer=_ans("chatgpt", chatgpt_text)),
        ],
    )
    return Debate(
        id="t", prompt="What?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[r1], status="in_progress", synthesis=None,
    )


class TestLLMJudgedBestR1Selector:
    async def test_returns_elder_from_judge_reply(self):
        judge = FakeElder(elder_id="claude", replies=["best: 2\nreason: Gemini strongest.\n"])
        selector = LLMJudgedBestR1Selector(judge_port=judge)
        pick = await selector.select(_debate_with_r1())
        assert isinstance(pick, BestR1Selection)
        assert pick.elder == "gemini"
        assert "Gemini strongest" in pick.reason

    async def test_index_one_maps_to_claude(self):
        judge = FakeElder(elder_id="claude", replies=["best: 1\nreason: claude.\n"])
        pick = await LLMJudgedBestR1Selector(judge_port=judge).select(_debate_with_r1())
        assert pick is not None and pick.elder == "claude"

    async def test_index_three_maps_to_chatgpt(self):
        judge = FakeElder(elder_id="claude", replies=["best: 3\nreason: chatgpt.\n"])
        pick = await LLMJudgedBestR1Selector(judge_port=judge).select(_debate_with_r1())
        assert pick is not None and pick.elder == "chatgpt"

    async def test_unparseable_judge_reply_falls_back_to_first_slot(self):
        judge = FakeElder(elder_id="claude", replies=["banana split\n"])
        pick = await LLMJudgedBestR1Selector(judge_port=judge).select(_debate_with_r1())
        assert pick is not None
        assert pick.elder == "claude"
        assert pick.reason == ""

    async def test_tolerates_markdown_fence(self):
        judge = FakeElder(
            elder_id="claude",
            replies=["```\nbest: 2\nreason: Gemini wins.\n```"],
        )
        pick = await LLMJudgedBestR1Selector(judge_port=judge).select(_debate_with_r1())
        assert pick is not None and pick.elder == "gemini"

    async def test_returns_none_when_no_rounds(self):
        judge = FakeElder(elder_id="claude", replies=["best: 1\nreason: x\n"])
        empty = Debate(
            id="t", prompt="x",
            pack=CouncilPack(name="bare", shared_context=None, personas={}),
            rounds=[], status="in_progress", synthesis=None,
        )
        assert await LLMJudgedBestR1Selector(judge_port=judge).select(empty) is None

    async def test_returns_none_when_all_r1_answers_empty(self):
        judge = FakeElder(elder_id="claude", replies=["best: 1\nreason: x\n"])
        d = _debate_with_r1(claude_text="", gemini_text="", chatgpt_text="   ")
        assert await LLMJudgedBestR1Selector(judge_port=judge).select(d) is None

    async def test_does_not_call_judge_on_empty_input(self):
        judge = FakeElder(elder_id="claude", replies=[])
        empty = Debate(
            id="t", prompt="x",
            pack=CouncilPack(name="bare", shared_context=None, personas={}),
            rounds=[], status="in_progress", synthesis=None,
        )
        result = await LLMJudgedBestR1Selector(judge_port=judge).select(empty)
        assert result is None
        assert judge.conversations == []
