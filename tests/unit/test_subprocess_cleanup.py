import asyncio
from unittest.mock import patch
import pytest

from council.adapters.elders._subprocess import SubprocessElder


async def test_ask_kills_subprocess_when_wait_for_raises_arbitrary_error(tmp_path):
    # Use a real small subprocess: /bin/cat which will wait indefinitely on stdin
    elder = SubprocessElder(
        elder_id="claude",
        binary="/bin/cat",
        build_args=lambda p: [],
    )

    # Patch wait_for to immediately raise a non-TimeoutError
    class BoomError(RuntimeError):
        pass

    async def fake_wait_for(coro, timeout):
        raise BoomError("simulated")

    with patch("council.adapters.elders._subprocess.asyncio.wait_for", fake_wait_for):
        with pytest.raises(BoomError):
            await elder.ask("anything")
    # If we got here without the event loop hanging, the process was killed.
