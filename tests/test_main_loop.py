import pytest
from jarvis.main_loop import Jarvis


def test_jarvis_initializes():
    jarvis = Jarvis()
    assert jarvis.api_manager is not None
    assert jarvis.voice is not None
    assert jarvis.browser is not None
    assert jarvis.automation is not None
    assert jarvis.blacklist_handler is not None
    assert jarvis.resume_handler is not None
    assert jarvis.task_manager is not None
    assert jarvis.prediction_engine is not None
    assert jarvis.context_selector is not None


def test_jarvis_cleanup():
    jarvis = Jarvis()
    jarvis.cleanup()
    assert jarvis.browser is not None
