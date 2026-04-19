import pytest

from council.app.tui.layout import (
    MIN_WIDTH_3COL,
    MIN_WIDTH_PER_ELDER,
    pick_layout,
)


def test_constants_match_spec():
    # Spec: at least 80 readable columns per elder × 3 elders = 240 total.
    assert MIN_WIDTH_PER_ELDER == 80
    assert MIN_WIDTH_3COL == 240


class TestPickLayoutAuto:
    def test_well_above_threshold_returns_columns(self):
        assert pick_layout(400, forced=None) == "columns"

    def test_exactly_at_threshold_returns_columns(self):
        assert pick_layout(240, forced=None) == "columns"

    def test_one_below_threshold_returns_tabs(self):
        assert pick_layout(239, forced=None) == "tabs"

    def test_narrow_terminal_returns_tabs(self):
        assert pick_layout(80, forced=None) == "tabs"


class TestPickLayoutForced:
    @pytest.mark.parametrize("width", [0, 80, 239, 240, 1000])
    def test_forced_tabs_overrides_width(self, width):
        assert pick_layout(width, forced="tabs") == "tabs"

    @pytest.mark.parametrize("width", [0, 80, 239, 240, 1000])
    def test_forced_columns_overrides_width(self, width):
        assert pick_layout(width, forced="columns") == "columns"
