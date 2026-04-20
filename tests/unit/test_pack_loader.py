from pathlib import Path
import pytest

from council.adapters.packs.filesystem import FilesystemPackLoader


@pytest.fixture
def packs_root(tmp_path: Path) -> Path:
    root = tmp_path / "packs"
    root.mkdir()
    return root


def test_loads_empty_pack(packs_root: Path):
    pack_dir = packs_root / "bare"
    pack_dir.mkdir()
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("bare")
    assert pack.name == "bare"
    assert pack.shared_context is None
    assert pack.personas == {}


def test_loads_shared_context(packs_root: Path):
    pack_dir = packs_root / "coo"
    pack_dir.mkdir()
    (pack_dir / "shared.md").write_text("You are my chief of staff.\n")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("coo")
    assert pack.shared_context == "You are my chief of staff."


def test_loads_per_elder_personas(packs_root: Path):
    pack_dir = packs_root / "exec"
    pack_dir.mkdir()
    (pack_dir / "claude.md").write_text("Legal advisor.")
    (pack_dir / "gemini.md").write_text("Engineer.")
    (pack_dir / "chatgpt.md").write_text("Marketer.")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("exec")
    assert pack.personas == {
        "ada": "Legal advisor.",
        "kai": "Engineer.",
        "mei": "Marketer.",
    }


def test_ignores_unknown_files(packs_root: Path):
    pack_dir = packs_root / "mixed"
    pack_dir.mkdir()
    (pack_dir / "shared.md").write_text("shared")
    (pack_dir / "random.txt").write_text("ignored")
    (pack_dir / "notes.md").write_text("also ignored")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("mixed")
    assert pack.shared_context == "shared"
    assert pack.personas == {}


def test_absolute_path_overrides_root(tmp_path: Path, packs_root: Path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "shared.md").write_text("custom")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load(str(elsewhere))
    assert pack.shared_context == "custom"
    assert pack.name == "elsewhere"


def test_missing_pack_raises(packs_root: Path):
    loader = FilesystemPackLoader(root=packs_root)
    with pytest.raises(FileNotFoundError):
        loader.load("nope")


def test_bare_name_is_resolved_under_root_even_if_cwd_has_same_name(
    packs_root: Path, tmp_path: Path, monkeypatch
):
    # A colliding entry exists in CWD but NOT under root
    (tmp_path / "decoy").mkdir()
    (tmp_path / "decoy" / "shared.md").write_text("from decoy")
    monkeypatch.chdir(tmp_path)

    loader = FilesystemPackLoader(root=packs_root)
    # Bare name "decoy" should resolve to packs_root/"decoy", which doesn't exist
    with pytest.raises(FileNotFoundError):
        loader.load("decoy")
