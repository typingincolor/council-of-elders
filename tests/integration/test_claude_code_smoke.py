import pytest

from council.adapters.elders.claude_code import ClaudeCodeAdapter


@pytest.mark.integration
async def test_claude_code_says_hi():
    elder = ClaudeCodeAdapter()
    if not await elder.health_check():
        pytest.skip("claude CLI not installed or not authenticated")
    reply = await elder.ask("Say exactly the word 'hi' and nothing else.", timeout_s=60)
    assert reply.strip()
