from __future__ import annotations

from council.app.headless.runner import run_headless


def main() -> None:
    from council.app.headless.cli import main as cli_main

    cli_main()


__all__ = ["main", "run_headless"]
