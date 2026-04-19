"""JsonFileStore.save must be atomic — a crash mid-write must not leave a
truncated file, and the target path must always contain either the old or
the new complete content, never a partial write."""

from pathlib import Path
from unittest.mock import patch

import pytest

from council.adapters.storage.json_file import JsonFileStore
from council.domain.models import CouncilPack, Debate


def _debate(id_="d1"):
    return Debate(
        id=id_,
        prompt="q",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


def test_save_writes_via_tmp_then_rename(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    store.save(_debate())
    # After save, the final file exists, and no stray .tmp remains.
    assert (tmp_path / "d1.json").is_file()
    assert not (tmp_path / "d1.json.tmp").exists()


def test_save_preserves_previous_version_if_write_fails(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    # First, a good save so the target exists.
    store.save(_debate())
    original = (tmp_path / "d1.json").read_text()

    # Now make os.replace raise after the tmp file is written.
    # The target must still contain the previous content — not be truncated.
    with patch(
        "council.adapters.storage.json_file.os.replace",
        side_effect=OSError("simulated rename failure"),
    ):
        d = _debate()
        d.status = "abandoned"  # a change we expect NOT to land
        with pytest.raises(OSError):
            store.save(d)

    # Target still holds the original content; the "abandoned" change did NOT land.
    assert (tmp_path / "d1.json").read_text() == original
    loaded = store.load("d1")
    assert loaded.status == "in_progress"


def test_save_still_round_trips_under_normal_conditions(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    d = _debate()
    d.status = "synthesized"
    store.save(d)
    loaded = store.load("d1")
    assert loaded.status == "synthesized"
