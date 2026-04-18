import pytest
from council.domain.convergence import ConvergencePolicy


@pytest.fixture
def policy():
    return ConvergencePolicy()


def test_parses_converged_yes(policy):
    text = "This is my answer.\n\nCONVERGED: yes"
    cleaned, agreed = policy.parse(text)
    assert cleaned == "This is my answer."
    assert agreed is True


def test_parses_converged_no(policy):
    text = "Here's my take.\nCONVERGED: no"
    cleaned, agreed = policy.parse(text)
    assert cleaned == "Here's my take."
    assert agreed is False


def test_missing_tag_returns_none(policy):
    text = "Forgot the tag."
    cleaned, agreed = policy.parse(text)
    assert cleaned == "Forgot the tag."
    assert agreed is None


def test_case_insensitive_and_whitespace_tolerant(policy):
    text = "answer\n  converged:   YES  "
    cleaned, agreed = policy.parse(text)
    assert cleaned == "answer"
    assert agreed is True


def test_only_strips_when_tag_is_last_nonblank_line(policy):
    text = "CONVERGED: yes is a weird way to start\nreal answer here"
    cleaned, agreed = policy.parse(text)
    # tag in the middle does not count
    assert agreed is None
    assert cleaned == text


def test_empty_input(policy):
    cleaned, agreed = policy.parse("")
    assert cleaned == ""
    assert agreed is None
