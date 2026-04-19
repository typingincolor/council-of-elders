from unittest.mock import patch

from council.app.tui.verbs import (
    FixedVerbChooser,
    RandomVerbChooser,
    VERB_POOL,
)


class TestVerbPool:
    def test_pool_contains_expected_verbs(self):
        assert "Pondering" in VERB_POOL
        assert "Deliberating" in VERB_POOL
        assert "Cogitating" in VERB_POOL
        assert len(VERB_POOL) == 12

    def test_pool_is_tuple_not_list(self):
        # immutable to prevent accidental mutation at runtime
        assert isinstance(VERB_POOL, tuple)


class TestFixedVerbChooser:
    def test_always_returns_the_fixed_verb(self):
        c = FixedVerbChooser("Pondering")
        assert c() == "Pondering"
        assert c() == "Pondering"


class TestRandomVerbChooser:
    def test_returns_a_verb_from_the_pool(self):
        c = RandomVerbChooser()
        # patch random.choice so we don't need to sample many times
        with patch("council.app.tui.verbs.random.choice", return_value="Noodling"):
            assert c() == "Noodling"

    def test_multiple_calls_all_return_pool_members(self):
        c = RandomVerbChooser()
        for _ in range(20):
            assert c() in VERB_POOL
