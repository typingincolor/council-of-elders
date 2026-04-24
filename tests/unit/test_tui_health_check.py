from council.adapters.elders.fake import FakeElder
from council.app.tui.health_check import HealthChecker
from council.app.tui.notices import CouncilNotices


class _StubLog:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, line: str) -> None:
        self.written.append(line)


def _notices() -> tuple[CouncilNotices, list[str]]:
    buf: list[str] = []
    return CouncilNotices(log=_StubLog(), buffer=buf), buf


_LABELS = {"ada": "Ada", "kai": "Kai", "mei": "Mei"}


class _RaisingElder:
    """Probe raises — must be treated as unhealthy."""

    def __init__(self) -> None:
        self.called = 0

    async def health_check(self) -> bool:
        self.called += 1
        raise RuntimeError("boom")


class TestHealthChecker:
    async def test_all_healthy_returns_false_and_writes_nothing(self):
        elders = {
            "ada": FakeElder(elder_id="ada", replies=[], healthy=True),
            "kai": FakeElder(elder_id="kai", replies=[], healthy=True),
            "mei": FakeElder(elder_id="mei", replies=[], healthy=True),
        }
        notices, buf = _notices()
        checker = HealthChecker(elders=elders, labels=_LABELS)

        all_down = await checker.run(notices)

        assert all_down is False
        assert buf == []

    async def test_some_unhealthy_writes_per_elder_notice_returns_false(self):
        elders = {
            "ada": FakeElder(elder_id="ada", replies=[], healthy=True),
            "kai": FakeElder(elder_id="kai", replies=[], healthy=False),
            "mei": FakeElder(elder_id="mei", replies=[], healthy=True),
        }
        notices, buf = _notices()
        checker = HealthChecker(elders=elders, labels=_LABELS)

        all_down = await checker.run(notices)

        assert all_down is False
        assert any("Kai CLI is unavailable" in line for line in buf)
        assert not any("Ada CLI is unavailable" in line for line in buf)
        # No "No elders available" red line when some are still healthy.
        assert not any("No elders available" in line for line in buf)

    async def test_all_unhealthy_returns_true_and_writes_red_followup(self):
        elders = {
            "ada": FakeElder(elder_id="ada", replies=[], healthy=False),
            "kai": FakeElder(elder_id="kai", replies=[], healthy=False),
            "mei": FakeElder(elder_id="mei", replies=[], healthy=False),
        }
        notices, buf = _notices()
        checker = HealthChecker(elders=elders, labels=_LABELS)

        all_down = await checker.run(notices)

        assert all_down is True
        assert any("No elders available" in line for line in buf)
        # All three per-elder notices present.
        for name in ("Ada", "Kai", "Mei"):
            assert any(f"{name} CLI is unavailable" in line for line in buf)

    async def test_probe_exception_treated_as_unhealthy(self):
        raising = _RaisingElder()
        elders = {
            "ada": raising,
            "kai": FakeElder(elder_id="kai", replies=[], healthy=True),
            "mei": FakeElder(elder_id="mei", replies=[], healthy=True),
        }
        notices, buf = _notices()
        checker = HealthChecker(elders=elders, labels=_LABELS)

        all_down = await checker.run(notices)

        assert all_down is False
        assert raising.called == 1
        assert any("Ada CLI is unavailable" in line for line in buf)
