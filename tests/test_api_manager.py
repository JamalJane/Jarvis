import pytest
from jarvis.config.api_manager import APIManager


def test_api_manager_initializes():
    manager = APIManager()
    assert len(manager.keys) >= 0


def test_get_status_returns_dict():
    manager = APIManager()
    status = manager.get_status()
    assert isinstance(status, dict)
    assert "current_key" in status
    assert "status" in status


def test_request_counts_initialized():
    manager = APIManager()
    assert all(count == 0 for count in manager.request_counts.values())
