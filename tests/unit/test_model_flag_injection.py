"""Each vendor adapter should inject its --model flag into argv when provided."""

from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter


class TestClaudeModelFlag:
    def test_no_model_gives_bare_argv(self):
        a = ClaudeCodeAdapter()
        assert a.build_args("hello") == ["-p", "hello"]

    def test_model_prepends_model_flag(self):
        a = ClaudeCodeAdapter(model="sonnet")
        assert a.build_args("hello") == ["--model", "sonnet", "-p", "hello"]


class TestGeminiModelFlag:
    def test_no_model_gives_bare_argv(self):
        a = GeminiCLIAdapter()
        assert a.build_args("hi") == ["-p", "hi"]

    def test_model_prepends_m_flag(self):
        a = GeminiCLIAdapter(model="gemini-2.5-flash")
        assert a.build_args("hi") == ["-m", "gemini-2.5-flash", "-p", "hi"]


class TestCodexModelFlag:
    def test_no_model_gives_exec_then_prompt(self):
        a = CodexCLIAdapter()
        assert a.build_args("hi") == ["exec", "hi"]

    def test_model_inserts_between_exec_and_prompt(self):
        a = CodexCLIAdapter(model="gpt-5-codex")
        assert a.build_args("hi") == ["exec", "-m", "gpt-5-codex", "hi"]
