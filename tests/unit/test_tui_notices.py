from council.app.tui.notices import CouncilNotices


class _StubLog:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, line: str) -> None:
        self.written.append(line)


class TestCouncilNoticesWrite:
    def test_appends_to_both_buffer_and_log(self):
        log = _StubLog()
        buffer: list[str] = []
        notices = CouncilNotices(log=log, buffer=buffer)

        notices.write("first")
        notices.write("second")

        assert buffer == ["first", "second"]
        assert log.written == ["first", "second"]


class TestCouncilNoticesDecisionHint:
    def test_r1_only_hint_mentions_keybindings(self):
        log = _StubLog()
        buffer: list[str] = []
        notices = CouncilNotices(log=log, buffer=buffer)

        notices.decision_hint("r1_only")

        line = buffer[-1]
        assert "R1 complete" in line
        # All four keybindings should be surfaced.
        for key in ("[d]", "[s]", "[c]", "[a]"):
            assert key in line

    def test_full_hint_mentions_r1_r2_complete(self):
        log = _StubLog()
        buffer: list[str] = []
        notices = CouncilNotices(log=log, buffer=buffer)

        notices.decision_hint("full")

        line = buffer[-1]
        assert "R1+R2 complete" in line
        assert "compare drafts" in line
