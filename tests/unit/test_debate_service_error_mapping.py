from datetime import datetime, timezone

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders._subprocess import ElderSubprocessError
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate


def _debate():
    return Debate(
        id="d1",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


class CliMissingElder:
    elder_id = "kai"

    async def ask(self, prompt, *, timeout_s=120.0):
        raise ElderSubprocessError("cli_missing", "kai")

    async def health_check(self):
        return False


async def test_cli_missing_preserves_error_kind():
    elders = {
        "ada": FakeElder(elder_id="ada", replies=["ok\nCONVERGED: yes"]),
        "kai": CliMissingElder(),
        "mei": FakeElder(elder_id="mei", replies=["ok\nCONVERGED: yes"]),
    }
    s = DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
    )
    r = await s.run_round(_debate())
    gem = next(t for t in r.turns if t.elder == "kai")
    assert gem.answer.error is not None
    assert gem.answer.error.kind == "cli_missing"
