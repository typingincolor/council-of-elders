from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.bootstrap import build_elders
from council.app.config import load_config
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
    *,
    using_openrouter: bool = False,
    max_rounds: int = 3,
) -> None:
    """Headless one-shot debate.

    Always runs R1 (silent initial) + R2 (cross-exam). Then optionally
    continues rounds until all elders converge or max_rounds is hit.
    max_rounds counts R1+R2 + any additional rounds; must be >= 2.
    """
    if max_rounds < 2:
        raise ValueError("max_rounds must be at least 2 (R1+R2 are mandatory)")

    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=pack,
        rounds=[],
        status="in_progress",
        synthesis=None,
    )
    svc = DebateService(elders=elders, store=store, clock=clock, bus=bus)

    # Opening exchange — always R1 + R2.
    await svc.run_round(debate)  # R1
    await svc.run_round(debate)  # R2

    # R3+ until convergence or max-rounds.
    while len(debate.rounds) < max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
        await svc.run_round(debate)

    # Print each round's turns in order.
    for r in debate.rounds:
        print(f"--- Round {r.number} ---")
        for t in r.turns:
            label = _LABELS[t.elder]
            if t.answer.error:
                print(f"[{label}] ERROR {t.answer.error.kind}: {t.answer.error.detail}\n")
            else:
                print(f"[{label}] {t.answer.text}\n")

    synth = await svc.synthesize(debate, by=synthesizer)
    print(f"[Synthesis by {_LABELS[synthesizer]}] {synth.text}")
    if using_openrouter:
        from council.adapters.elders.openrouter import (
            OpenRouterAdapter,
            format_cost_notice,
        )

        any_or = next(
            (e for e in elders.values() if isinstance(e, OpenRouterAdapter)),
            None,
        )
        used, limit = (0.0, None)
        if any_or is not None:
            used, limit = await any_or.fetch_credits()
        total = sum(e.session_cost_usd for e in elders.values() if isinstance(e, OpenRouterAdapter))
        line = format_cost_notice(
            elders=elders,
            round_cost_delta_usd=total,  # for headless a single "round" = whole session
            credits_used=used,
            credits_limit=limit,
        )
        print(line)


def _max_rounds_type(value: str) -> int:
    n = int(value)
    if n < 2:
        raise argparse.ArgumentTypeError("--max-rounds must be at least 2 (R1+R2 are mandatory)")
    return n


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
    parser.add_argument(
        "--max-rounds",
        type=_max_rounds_type,
        default=3,
        help="Upper bound on total rounds (R1+R2 + optional R3+). Minimum 2; default 3.",
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    pack = (
        FilesystemPackLoader(root=packs_root).load(args.pack)
        if (packs_root / args.pack).is_dir()
        else CouncilPack(name=args.pack, shared_context=None, personas={})
    )

    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "claude": args.claude_model,
        "gemini": args.gemini_model,
        "chatgpt": args.codex_model,
    }
    elders, using_openrouter = build_elders(config, cli_models=cli_models)
    asyncio.run(
        run_headless(
            prompt=args.prompt,
            pack=pack,
            elders=elders,
            store=JsonFileStore(root=Path(args.store_root)),
            clock=SystemClock(),
            bus=InMemoryBus(),
            synthesizer=args.synthesizer,
            using_openrouter=using_openrouter,
            max_rounds=args.max_rounds,
        )
    )
