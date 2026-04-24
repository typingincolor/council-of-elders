from __future__ import annotations

import argparse
from pathlib import Path

from council.adapters.clock.system import SystemClock
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.bootstrap import build_elders
from council.app.config import load_config
from council.app.tui.app import CouncilApp
from council.domain.models import ElderId


def _build_parser() -> argparse.ArgumentParser:
    import os

    parser = argparse.ArgumentParser(prog="council")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
    parser.add_argument("--reports-root", default=str(Path.home() / ".council" / "reports"))
    parser.add_argument("--claude-model", default=os.environ.get("COUNCIL_CLAUDE_MODEL"))
    parser.add_argument("--gemini-model", default=os.environ.get("COUNCIL_GEMINI_MODEL"))
    parser.add_argument("--codex-model", default=os.environ.get("COUNCIL_CODEX_MODEL"))
    parser.add_argument("--mode", choices=["r1_only", "full"], default="r1_only")
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    (packs_root / args.pack).mkdir(exist_ok=True)

    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "ada": args.claude_model,
        "kai": args.gemini_model,
        "mei": args.codex_model,
    }
    elders, using_openrouter, _roster_spec = build_elders(config, cli_models=cli_models)

    from council.adapters.storage.report_file import ReportFileStore

    app = CouncilApp(
        elders=elders,
        store=JsonFileStore(root=Path(args.store_root)),
        clock=SystemClock(),
        pack_loader=FilesystemPackLoader(root=packs_root),
        pack_name=args.pack,
        using_openrouter=using_openrouter,
        report_store=ReportFileStore(root=Path(args.reports_root)),
        mode=args.mode,
    )
    app.run()
