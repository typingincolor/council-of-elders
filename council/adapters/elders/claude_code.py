from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if "not logged in" in s or "unauthorized" in s or "authenticat" in s:
        return "auth_failed"
    return "nonzero_exit"


def _build_args(model: str | None):
    def _args(prompt: str) -> list[str]:
        args: list[str] = []
        if model:
            args += ["--model", model]
        args += ["-p", prompt]
        return args

    return _args


class ClaudeCodeAdapter(SubprocessElder):
    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            elder_id="ada",
            binary="ada",
            build_args=_build_args(model),
            classify_stderr=_classify,
        )
