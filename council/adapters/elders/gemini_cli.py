from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder

# Known chrome lines that the `gemini` CLI emits on stdout before the actual reply.
# The CLI sometimes prints these concatenated with the reply on the same line
# (no trailing newline), so we strip them from the start of the output.
_NOISE_PREFIXES = (
    "MCP issues detected. Run /mcp list for status.",
    "Loaded cached credentials.",
)


def _sanitize(raw: str) -> str:
    out = raw.lstrip()
    changed = True
    while changed:
        changed = False
        for prefix in _NOISE_PREFIXES:
            if out.startswith(prefix):
                out = out[len(prefix):].lstrip()
                changed = True
    return out


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


def _build_args(model: str | None):
    def _args(prompt: str) -> list[str]:
        args: list[str] = []
        if model:
            args += ["-m", model]
        args += ["-p", prompt]
        return args

    return _args


class GeminiCLIAdapter(SubprocessElder):
    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            elder_id="gemini",
            binary="gemini",
            build_args=_build_args(model),
            classify_stderr=_classify,
            sanitize_stdout=_sanitize,
        )
