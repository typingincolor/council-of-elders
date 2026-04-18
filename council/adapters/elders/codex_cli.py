from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if "not signed in" in s or "login" in s or "unauthorized" in s:
        return "auth_failed"
    return "nonzero_exit"


class CodexCLIAdapter(SubprocessElder):
    def __init__(self) -> None:
        super().__init__(
            elder_id="chatgpt",
            binary="codex",
            build_args=lambda prompt: ["exec", prompt],
            classify_stderr=_classify,
        )
