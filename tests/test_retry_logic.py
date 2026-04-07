import pytest
from jarvis.flows.retry_logic import RetryHandler


def test_retry_handler_initializes():
    handler = RetryHandler()
    assert handler.max_retries == 5
    assert handler.base_delay == 2


def test_retry_handler_custom_values():
    handler = RetryHandler(max_retries=3, base_delay=1)
    assert handler.max_retries == 3
    assert handler.base_delay == 1


def test_retry_handler_succeeds_first_attempt():
    handler = RetryHandler(max_retries=3, base_delay=0)
    result = handler.execute_with_retry(lambda: "success")
    assert result == "success"


def test_retry_handler_fails_all_attempts():
    handler = RetryHandler(max_retries=2, base_delay=0)
    call_count = 0
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Test error")

    result = handler.execute_with_retry(failing_func)
    assert result is None
    assert call_count == 2


def test_verify_result():
    handler = RetryHandler()
    assert handler._verify_result("value") is True
    assert handler._verify_result(None) is False
