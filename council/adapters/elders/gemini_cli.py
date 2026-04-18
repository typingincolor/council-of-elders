from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if (
        "quota" in s
        or "rate limit" in s
        or "rate-limit" in s
        or "exhausted" in s
        or "too many requests" in s
        or "resource_exhausted" in s
    ):
        return "quota_exhausted"
    if "credential" in s or "login" in s or "unauthenticated" in s:
        return "auth_failed"
    return "nonzero_exit"


class GeminiCLIAdapter(SubprocessElder):
    def __init__(self) -> None:
        super().__init__(
            elder_id="gemini",
            binary="gemini",
            build_args=lambda prompt: ["-p", prompt],
            classify_stderr=_classify,
        )
