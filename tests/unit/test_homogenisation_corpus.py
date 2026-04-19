from pathlib import Path

from council.experiments.homogenisation.corpus import CorpusPrompt, load_corpus


def test_load_corpus_returns_all_eight_prompts(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(
        '{"prompts": ['
        '{"id": "p1", "shape": "headline", "prompt": "Q1?"},'
        '{"id": "p2", "shape": "summary", "prompt": "Q2?"}'
        "]}"
    )
    prompts = load_corpus(path)
    assert len(prompts) == 2
    assert prompts[0] == CorpusPrompt(id="p1", shape="headline", prompt="Q1?")
    assert prompts[1].shape == "summary"


def test_load_corpus_rejects_missing_fields(tmp_path: Path) -> None:
    import pytest

    path = tmp_path / "bad.json"
    path.write_text('{"prompts": [{"id": "p1", "prompt": "Q1?"}]}')  # missing shape
    with pytest.raises(KeyError):
        load_corpus(path)


def test_real_corpus_has_eight_prompts_with_unique_ids() -> None:
    path = Path(__file__).parents[2] / "scripts" / "homogenisation_corpus.json"
    prompts = load_corpus(path)
    assert len(prompts) == 8
    ids = [p.id for p in prompts]
    assert len(set(ids)) == 8
