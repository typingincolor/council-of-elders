from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if "not logged in" in s or "unauthorized" in s or "authenticat" in s:
        return "auth_failed"
    return "nonzero_exit"


class ClaudeCodeAdapter(SubprocessElder):
    def __init__(self) -> None:
        super().__init__(
            elder_id="claude",
            binary="claude",
            build_args=lambda prompt: ["-p", prompt],
            classify_stderr=_classify,
        )
