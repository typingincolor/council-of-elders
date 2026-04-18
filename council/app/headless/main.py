from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate, ElderId
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore

_LABELS: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


async def run_headless(
    prompt: str,
    pack: CouncilPack,
    elders: dict[ElderId, ElderPort],
    store: TranscriptStore,
    clock: Clock,
    bus: EventBus,
    synthesizer: ElderId,
) -> None:
    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=pack,
        rounds=[],
        status="in_progress",
        synthesis=None,
    )
    svc = DebateService(elders=elders, store=store, clock=clock, bus=bus)
    r = await svc.run_round(debate)
    for t in r.turns:
        label = _LABELS[t.elder]
        if t.answer.error:
            print(f"[{label}] ERROR {t.answer.error.kind}: {t.answer.error.detail}\n")
        else:
            print(f"[{label}] {t.answer.text}\n")
    synth = await svc.synthesize(debate, by=synthesizer)
    print(f"[Synthesis by {_LABELS[synthesizer]}] {synth.text}")


def main() -> None:
    import os

    parser = argparse.ArgumentParser(prog="council-headless")
    parser.add_argument("prompt")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--synthesizer", choices=["claude", "gemini", "chatgpt"], default="claude")
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
    parser.add_argument(
        "--claude-model",
        default=os.environ.get("COUNCIL_CLAUDE_MODEL"),
        help="Model alias or full name passed to `claude --model` (e.g. sonnet, opus).",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("COUNCIL_GEMINI_MODEL"),
        help="Model name passed to `gemini -m` (e.g. gemini-2.5-flash — recommended; Pro has tight quota).",
    )
    parser.add_argument(
        "--codex-model",
        default=os.environ.get("COUNCIL_CODEX_MODEL"),
        help="Model name passed to `codex exec -m` (e.g. gpt-5-codex).",
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    pack = (
        FilesystemPackLoader(root=packs_root).load(args.pack)
        if (packs_root / args.pack).is_dir()
        else CouncilPack(name=args.pack, shared_context=None, personas={})
    )

    elders: dict[ElderId, ElderPort] = {
        "claude": ClaudeCodeAdapter(model=args.claude_model),
        "gemini": GeminiCLIAdapter(model=args.gemini_model),
        "chatgpt": CodexCLIAdapter(model=args.codex_model),
    }
    asyncio.run(
        run_headless(
            prompt=args.prompt,
            pack=pack,
            elders=elders,
            store=JsonFileStore(root=Path(args.store_root)),
            clock=SystemClock(),
            bus=InMemoryBus(),
            synthesizer=args.synthesizer,
        )
    )
