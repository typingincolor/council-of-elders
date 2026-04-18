from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Callable

from council.domain.models import ElderId


class ElderSubprocessError(Exception):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


@dataclass
class SubprocessElder:
    """Reusable base for shelling out to a vendor CLI.

    Concrete adapters fill in `binary`, `build_args`, and
    `classify_stderr` (to distinguish auth_failed from other nonzero exits).
    """

    elder_id: ElderId
    binary: str
    build_args: Callable[[str], list[str]]
    classify_stderr: Callable[[str], str] = lambda s: "nonzero_exit"

    async def ask(self, prompt: str, *, timeout_s: float = 120.0) -> str:
        if shutil.which(self.binary) is None:
            raise ElderSubprocessError("cli_missing", self.binary)
        proc = await asyncio.create_subprocess_exec(
            self.binary,
            *self.build_args(prompt),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except BaseException:
            # TimeoutError OR anything else (OSError, cancellation, ...)
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode != 0:
            detail = (stderr or b"").decode(errors="replace")[-400:]
            kind = self.classify_stderr(detail)
            raise ElderSubprocessError(kind, detail)
        return (stdout or b"").decode(errors="replace")

    async def health_check(self) -> bool:
        if shutil.which(self.binary) is None:
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError):
            return False
        try:
            rc = await asyncio.wait_for(proc.wait(), timeout=5.0)
            return rc == 0
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False
