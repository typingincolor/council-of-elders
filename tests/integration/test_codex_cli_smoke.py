import pytest

from council.adapters.elders.codex_cli import CodexCLIAdapter


@pytest.mark.integration
async def test_codex_cli_says_hi():
    elder = CodexCLIAdapter()
    if not await elder.health_check():
        pytest.skip("codex CLI not installed or not authenticated")
    reply = await elder.ask("Say exactly the word 'hi' and nothing else.", timeout_s=60)
    assert reply.strip()
