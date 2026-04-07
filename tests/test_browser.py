import pytest
from jarvis.core.browser import BrowserController


def test_browser_controller_initializes():
    controller = BrowserController()
    assert controller.headless is False
    assert controller.driver is None
    assert controller.wait is None


def test_browser_controller_headless():
    controller = BrowserController(headless=True)
    assert controller.headless is True


def test_browser_is_not_running_initially():
    controller = BrowserController()
    assert controller.is_running() is False


def test_browser_close_when_not_started():
    controller = BrowserController()
    controller.close()
    assert controller.is_running() is False
