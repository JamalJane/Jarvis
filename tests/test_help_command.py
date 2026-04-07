import pytest
from jarvis.flows.help_command import show_help, handle_help_command, is_help_command


def test_handle_help_command_with_help():
    result = handle_help_command("/help")
    assert result is True


def test_handle_help_command_with_help_word():
    result = handle_help_command("help")
    assert result is True


def test_handle_help_command_with_question_mark():
    result = handle_help_command("?")
    assert result is True


def test_handle_help_command_with_other():
    result = handle_help_command("go to google")
    assert result is False


def test_is_help_command():
    assert is_help_command("/help") is True
    assert is_help_command("help") is True
    assert is_help_command("?") is True
    assert is_help_command("other command") is False
