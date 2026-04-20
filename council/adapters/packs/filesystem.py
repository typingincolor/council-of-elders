from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from council.domain.models import CouncilPack, ElderId

# Iteration order matters: legacy names are read FIRST, then the current
# names, so a current-name file (e.g. ada.md) overrides a legacy one
# (claude.md) when both exist in the same pack.
_ELDER_FILES: dict[str, ElderId] = {
    "claude.md": "ada",
    "gemini.md": "kai",
    "chatgpt.md": "mei",
    "ada.md": "ada",
    "kai.md": "kai",
    "mei.md": "mei",
}


@dataclass
class FilesystemPackLoader:
    root: Path

    def load(self, pack_name_or_path: str) -> CouncilPack:
        p = Path(pack_name_or_path)
        if p.is_absolute():
            pack_dir = p
            name = pack_dir.name
        else:
            pack_dir = self.root / pack_name_or_path
            name = pack_name_or_path
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"Council pack not found: {pack_dir}")

        shared_path = pack_dir / "shared.md"
        shared = shared_path.read_text(encoding="utf-8").strip() if shared_path.is_file() else None
        personas: dict[ElderId, str] = {}
        for filename, elder in _ELDER_FILES.items():
            f = pack_dir / filename
            if f.is_file():
                personas[elder] = f.read_text(encoding="utf-8").strip()

        return CouncilPack(name=name, shared_context=shared, personas=personas)
