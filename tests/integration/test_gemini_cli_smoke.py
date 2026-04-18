import pytest

from council.adapters.elders.gemini_cli import GeminiCLIAdapter


@pytest.mark.integration
async def test_gemini_cli_says_hi():
    elder = GeminiCLIAdapter()
    if not await elder.health_check():
        pytest.skip("gemini CLI not installed or not authenticated")
    reply = await elder.ask("Say exactly the word 'hi' and nothing else.", timeout_s=60)
    assert reply.strip()
