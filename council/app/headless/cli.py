from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.bootstrap import build_elders
from council.app.config import load_config
from council.app.headless.runner import run_headless
from council.domain.debate_policy import DebatePolicy, PolicyMode
from council.domain.models import CouncilPack, ElderId
from council.domain.ports import ElderPort

_FIXED_POLICY_ROUNDS: dict[PolicyMode, int] = {
    "best_r1_only": 1,
    "r1_only": 1,
    "single_critique": 2,
}


def _max_rounds_type(value: str) -> int:
    n = int(value)
    if n < 2:
        raise argparse.ArgumentTypeError("--max-rounds must be at least 2 (R1+R2 are mandatory)")
    return n


def _policy_override_from_args(mode: str, max_rounds: int) -> DebatePolicy | None:
    if mode == "auto":
        return None
    pm: PolicyMode = mode  # type: ignore[assignment]
    # r1_only: R1 then synthesise, skip R2+. Experimentally the strongest
    # shape for diverse rosters (see 2026-04-20-226f, 2026-04-21-f13d).
    return DebatePolicy(
        mode=pm,
        max_rounds=max_rounds if mode == "full_debate" else _FIXED_POLICY_ROUNDS[pm],
        synthesise=mode != "best_r1_only",
        always_compute_best_r1=True,
        warning=None,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="council-headless")
    parser.add_argument("prompt")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--synthesizer", choices=["ada", "kai", "mei"], default="ada")
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
    parser.add_argument(
        "--claude-model",
        default=os.environ.get("COUNCIL_CLAUDE_MODEL"),
        help="Model alias or full name passed to `claude --model` (e.g. sonnet, opus).",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("COUNCIL_GEMINI_MODEL"),
        help="Model name passed to `gemini -m` (e.g. gemini-2.5-flash — recommended).",
    )
    parser.add_argument(
        "--codex-model",
        default=os.environ.get("COUNCIL_CODEX_MODEL"),
        help="Model name passed to `codex exec -m` (e.g. gpt-5-codex).",
    )
    parser.add_argument(
        "--max-rounds",
        type=_max_rounds_type,
        default=6,
        help=(
            "Upper bound on rounds for full_debate mode. Ignored in other "
            "policy modes. Minimum 2; default 6."
        ),
    )
    parser.add_argument(
        "--policy",
        choices=["auto", "best_r1_only", "r1_only", "single_critique", "full_debate"],
        default="auto",
        help=(
            "Pipeline mode. 'auto' (default) picks best_r1_only / "
            "single_critique / full_debate based on roster diversity. "
            "'r1_only' runs R1 then synthesises with no debate rounds; "
            "'best_r1_only' skips synthesis."
        ),
    )
    parser.add_argument(
        "--synthesise",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Override whether to synthesise after debate rounds. "
            "Default follows policy choice; pass --no-synthesise to skip."
        ),
    )
    parser.add_argument(
        "--reports-root",
        default=str(Path.home() / ".council" / "reports"),
        help="Directory where debate reports are saved as markdown.",
    )
    parser.add_argument(
        "--summaries-root",
        default=str(Path.home() / ".council" / "summaries"),
        help="Directory where per-debate run_summary.json files are saved.",
    )
    return parser


def _load_pack(pack_name: str, packs_root: Path) -> CouncilPack:
    packs_root.mkdir(parents=True, exist_ok=True)
    if (packs_root / pack_name).is_dir():
        return FilesystemPackLoader(root=packs_root).load(pack_name)
    return CouncilPack(name=pack_name, shared_context=None, personas={})


def _build_openrouter_judges(
    *,
    using_openrouter: bool,
    api_key: str | None,
) -> tuple[ElderPort | None, list[tuple[str, ElderPort]] | None]:
    if not using_openrouter or not api_key:
        return None, None

    from council.adapters.elders.openrouter import OpenRouterAdapter

    # Best-R1 uses a single cheap judge. Preference uses multi-judge
    # because preference verdicts are more exposed to judge-family bias.
    best_r1_judge: ElderPort = OpenRouterAdapter(
        elder_id="ada",
        model="google/gemini-2.5-flash",
        api_key=api_key,
    )
    preference_judges: list[tuple[str, ElderPort]] = [
        (
            "google/gemini-2.5-flash",
            OpenRouterAdapter(
                elder_id="ada",
                model="google/gemini-2.5-flash",
                api_key=api_key,
            ),
        ),
        (
            "anthropic/claude-haiku-4.5",
            OpenRouterAdapter(
                elder_id="ada",
                model="anthropic/claude-haiku-4.5",
                api_key=api_key,
            ),
        ),
    ]
    return best_r1_judge, preference_judges


def main() -> None:
    args = _build_parser().parse_args()

    packs_root = Path(args.packs_root)
    pack = _load_pack(args.pack, packs_root)

    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "ada": args.claude_model,
        "kai": args.gemini_model,
        "mei": args.codex_model,
    }
    elders, using_openrouter, roster_spec = build_elders(config, cli_models=cli_models)
    from council.adapters.storage.report_file import ReportFileStore

    best_r1_judge, preference_judges = _build_openrouter_judges(
        using_openrouter=using_openrouter,
        api_key=config.openrouter_api_key,
    )

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
            report_store=ReportFileStore(root=Path(args.reports_root)),
            best_r1_judge=best_r1_judge,
            preference_judges=preference_judges,
            policy=_policy_override_from_args(args.policy, args.max_rounds),
            roster_spec=roster_spec,
            run_summary_root=Path(args.summaries_root),
            synthesise_override=args.synthesise,
        )
    )
