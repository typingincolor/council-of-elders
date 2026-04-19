import pytest

from council.adapters.elders._flatten import flatten_conversation
from council.domain.models import Message


def test_user_only_single_turn():
    conv = [Message("user", "What is 2+2?")]
    assert flatten_conversation(conv) == "USER:\nWhat is 2+2?"


def test_system_user_assistant_user():
    conv = [
        Message("system", "You are helpful."),
        Message("user", "Hi"),
        Message("assistant", "Hello!"),
        Message("user", "Explain gravity."),
    ]
    expected = (
        "SYSTEM:\nYou are helpful.\n\n"
        "USER:\nHi\n\n"
        "ASSISTANT:\nHello!\n\n"
        "USER:\nExplain gravity."
    )
    assert flatten_conversation(conv) == expected


def test_omits_system_when_absent():
    conv = [
        Message("user", "Hi"),
        Message("assistant", "Hello!"),
        Message("user", "Bye"),
    ]
    out = flatten_conversation(conv)
    assert out.startswith("USER:\nHi")
    assert "SYSTEM:" not in out


def test_empty_raises():
    with pytest.raises(ValueError):
        flatten_conversation([])
