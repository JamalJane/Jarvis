import pytest
from jarvis.flows.startup import load_startup_summary, display_api_status
from jarvis.config.api_manager import APIManager


def test_load_startup_summary_returns_string():
    result = load_startup_summary()
    assert isinstance(result, str)


def test_display_api_status_runs_without_error():
    manager = APIManager()
    display_api_status(manager)
