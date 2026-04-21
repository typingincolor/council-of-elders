"""Tests for DebateService.synthesize(synthesis_prompt_override=...)."""

from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)


def _ans(elder, text):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


def _debate_with_r1() -> Debate:
    return Debate(
        id="t",
        prompt="What should I do?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[
            Round(
                number=1,
                turns=[
                    Turn(elder="ada", answer=_ans("ada", "Ada R1.")),
                    Turn(elder="kai", answer=_ans("kai", "Kai R1.")),
                    Turn(elder="mei", answer=_ans("mei", "Mei R1.")),
                ],
            )
        ],
        status="in_progress",
        synthesis=None,
    )


async def test_override_replaces_the_default_prompt():
    """When synthesis_prompt_override is provided, that exact string goes
    to the elder — not the PromptBuilder.build_synthesis output.
    """
    elder = FakeElder(elder_id="ada", replies=["the final answer."])
    svc = DebateService(
        elders={"ada": elder, "kai": elder, "mei": elder},
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
    )

    override = "CUSTOM SYNTHESIS PROMPT — sentinel text for assertion."
    await svc.synthesize(_debate_with_r1(), "ada", synthesis_prompt_override=override)

    # FakeElder recorded the conversation. The override must be the sole user message.
    assert len(elder.conversations) == 1
    conv = elder.conversations[0]
    assert conv[0].content == override


async def test_default_used_when_override_is_none():
    elder = FakeElder(elder_id="ada", replies=["ANSWER:\nok.\n\nWHY:\nfine.\n"])
    svc = DebateService(
        elders={"ada": elder, "kai": elder, "mei": elder},
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 20, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
    )
    await svc.synthesize(_debate_with_r1(), "ada")  # no override
    conv = elder.conversations[0]
    assert "ANSWER:" in conv[0].content
    assert "DISAGREEMENTS:" in conv[0].content


async def test_alt_synthesis_prompt_text_contains_no_labels():
    from council.domain.prompting import ALT_SYNTHESIS_PROMPT, build_alt_synthesis

    d = _debate_with_r1()
    prompt = build_alt_synthesis(d, "ada")
    assert "Synthesize, do not select" in prompt
    assert "ANSWER:" not in ALT_SYNTHESIS_PROMPT
    assert "WHY:" not in ALT_SYNTHESIS_PROMPT
    assert "DISAGREEMENTS:" not in ALT_SYNTHESIS_PROMPT
    assert d.prompt in prompt
