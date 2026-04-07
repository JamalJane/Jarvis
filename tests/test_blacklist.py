import pytest
from jarvis.config.blacklist import BlacklistChecker
from jarvis.flows.blacklist_action import BlacklistHandler


def test_blacklist_checker_initializes():
    checker = BlacklistChecker()
    assert len(checker.blacklisted_patterns) > 0


def test_is_blacklisted_returns_true_for_blocked():
    checker = BlacklistChecker()
    assert checker.is_blacklisted("delete_files test") is True
    assert checker.is_blacklisted("format_disk now") is True


def test_is_blacklisted_returns_false_for_allowed():
    checker = BlacklistChecker()
    assert checker.is_blacklisted("click the button") is False
    assert checker.is_blacklisted("go to google.com") is False


def test_add_pattern():
    checker = BlacklistChecker()
    checker.add_pattern("custom_block")
    assert checker.is_blacklisted("custom_block test") is True


def test_remove_pattern():
    checker = BlacklistChecker()
    checker.remove_pattern("delete_files")
    assert checker.is_blacklisted("delete_files test") is False


def test_get_blacklist():
    checker = BlacklistChecker()
    patterns = checker.get_blacklist()
    assert isinstance(patterns, list)
    assert "delete_files" in patterns


def test_blacklist_handler_initializes():
    handler = BlacklistHandler()
    assert handler.checker is not None


def test_blacklist_handler_is_blocked():
    handler = BlacklistHandler()
    assert handler.is_blocked("delete_files") is True
    assert handler.is_blocked("safe_action") is False
