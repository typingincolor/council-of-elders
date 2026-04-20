import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def mod():
    """Load the script module directly so we can unit-test its helpers."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "judge_replication.py"
    spec = importlib.util.spec_from_file_location("judge_replication_script", path)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["judge_replication_script"] = m
    spec.loader.exec_module(m)
    return m


class TestSlug:
    def test_slash_becomes_dash(self, mod):
        assert mod._slug("anthropic/claude-sonnet-4.5") == "anthropic-claude-sonnet-4-5"

    def test_strips_leading_and_trailing_dashes(self, mod):
        assert mod._slug("/foo/") == "foo"

    def test_collapses_runs(self, mod):
        assert mod._slug("openai//gpt--5") == "openai-gpt-5"

    def test_case_folded(self, mod):
        assert mod._slug("OpenAI/GPT-5") == "openai-gpt-5"


class TestCli:
    def test_parser_accepts_required_flags(self, mod, monkeypatch):
        # Dry-run the argparse path without actually calling _cmd_replicate.
        called_with = {}

        def fake_run(coro):
            # Inspect the args from the coroutine's closure.
            called_with["ran"] = True
            coro.close()

        monkeypatch.setattr(mod.asyncio, "run", fake_run)
        monkeypatch.setattr(
            mod.sys,
            "argv",
            [
                "judge_replication",
                "--run-id",
                "rid",
                "--judge-models",
                "openai/gpt-5,anthropic/claude-sonnet-4.5",
            ],
        )
        mod.main()
        assert called_with["ran"] is True

    def test_parser_rejects_missing_run_id(self, mod, monkeypatch):
        monkeypatch.setattr(
            mod.sys,
            "argv",
            ["judge_replication", "--judge-models", "openai/gpt-5"],
        )
        with pytest.raises(SystemExit):
            mod.main()
