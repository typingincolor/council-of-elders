from __future__ import annotations

import re


class ConvergencePolicy:
    _TAG_RE = re.compile(r"^\s*converged\s*:\s*(yes|no)\s*$", re.IGNORECASE)

    def parse(self, raw: str) -> tuple[str, bool | None]:
        if not raw:
            return "", None
        lines = raw.splitlines()
        # find the last non-blank line
        last_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip():
                last_idx = i
                break
        if last_idx is None:
            return raw, None
        m = self._TAG_RE.match(lines[last_idx])
        if not m:
            return raw, None
        agreed = m.group(1).lower() == "yes"
        cleaned = "\n".join(lines[:last_idx]).rstrip()
        return cleaned, agreed
