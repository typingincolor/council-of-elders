from council.adapters.elders.fake import FakeElder
from council.app.tui.cost_notifier import CostNotifier
from council.app.tui.notices import CouncilNotices


class _StubLog:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, line: str) -> None:
        self.written.append(line)


def _notices():
    buf: list[str] = []
    return CouncilNotices(log=_StubLog(), buffer=buf), buf


class _FakeOpenRouter:
    """Minimal stand-in for OpenRouterAdapter that satisfies the
    isinstance check by actually *being* OpenRouterAdapter — we can't
    fake that without patching the symbol. Instead the CostNotifier
    tests exercise the non-OpenRouter (subprocess-only) path, which
    is the common case for tests.
    """


class TestCostNotifierWithoutOpenRouter:
    async def test_emit_writes_a_line_with_zero_delta(self):
        # No OpenRouter adapters present → delta is 0, credits are
        # (0.0, None), format_cost_notice still produces a notice.
        elders = {
            "ada": FakeElder(elder_id="ada", replies=[]),
            "kai": FakeElder(elder_id="kai", replies=[]),
            "mei": FakeElder(elder_id="mei", replies=[]),
        }
        notifier = CostNotifier(elders=elders)
        notices, buf = _notices()

        await notifier.emit(notices)

        assert len(buf) == 1
        # Line is a blue-wrapped notice.
        assert buf[0].startswith("[blue]") and buf[0].endswith("[/blue]")

    async def test_prev_total_starts_at_zero(self):
        notifier = CostNotifier(
            elders={"ada": FakeElder(elder_id="ada", replies=[])},
        )
        assert notifier._prev_total == 0.0


class TestCostNotifierDeltaComputation:
    async def test_delta_accumulates_across_calls(self, monkeypatch):
        """Patch the OpenRouter symbol + format_cost_notice to observe
        that the notifier subtracts _prev_total on each emit. This is
        the one piece of CostNotifier logic that matters — the rest is
        mostly glue.
        """
        captured_deltas: list[float] = []

        class _FakeAdapter:
            def __init__(self, cost: float):
                self.session_cost_usd = cost

            async def fetch_credits(self):
                return (0.0, None)

        # Monkeypatch the isinstance check target and the formatter in
        # the cost_notifier module's namespace — imports happen inside
        # .emit() via ``from … import`` so we patch the source module.
        import council.adapters.elders.openrouter as or_mod

        monkeypatch.setattr(or_mod, "OpenRouterAdapter", _FakeAdapter)

        def _fmt(*, elders, round_cost_delta_usd, credits_used, credits_limit):
            captured_deltas.append(round_cost_delta_usd)
            return "ok"

        monkeypatch.setattr(or_mod, "format_cost_notice", _fmt)

        a1 = _FakeAdapter(cost=1.0)
        a2 = _FakeAdapter(cost=2.5)
        notifier = CostNotifier(elders={"ada": a1, "kai": a2})
        notices, _ = _notices()

        # First emit: delta = (1.0 + 2.5) - 0 = 3.5
        await notifier.emit(notices)

        # Mutate the cost totals to simulate more LLM work done.
        a1.session_cost_usd = 1.5
        a2.session_cost_usd = 3.0

        # Second emit: delta = (1.5 + 3.0) - 3.5 = 1.0
        await notifier.emit(notices)

        assert captured_deltas == [3.5, 1.0]
        assert notifier._prev_total == 4.5
