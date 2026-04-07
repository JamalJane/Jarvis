import logging
import time
from typing import Callable, Any, Optional
from jarvis.config.constants import MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)


class RetryHandler:
    def __init__(self, max_retries: int = None, base_delay: int = None):
        self.max_retries = max_retries or MAX_RETRIES
        self.base_delay = base_delay or RETRY_BASE_DELAY

    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Optional[Any]:
        attempt = 0
        last_error = None

        while attempt < self.max_retries:
            try:
                result = func(*args, **kwargs)
                if self._verify_result(result):
                    logger.info(f"Function succeeded on attempt {attempt + 1}")
                    return result
                else:
                    logger.warning(f"Attempt {attempt + 1} returned invalid result")
                    raise ValueError("Result verification failed")
            except Exception as e:
                attempt += 1
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")

                if attempt >= self.max_retries:
                    logger.error(f"Max retries ({self.max_retries}) exceeded")
                    return self._handle_max_retries_exceeded(func, *args, **kwargs)

                delay = self.base_delay ** attempt
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)

        return None

    def _verify_result(self, result: Any) -> bool:
        return result is not None

    def _handle_max_retries_exceeded(self, func: Callable, *args, **kwargs) -> Optional[Any]:
        logger.error("Max retries exceeded")
        return None

    def execute_with_manual_fallback(self, func: Callable, *args, **kwargs) -> Optional[Any]:
        result = self.execute_with_retry(func, *args, **kwargs)
        if result is not None:
            return result
        return self._manual_input()

    def _manual_input(self) -> str:
        try:
            return input("Enter action manually (or press Enter to skip): ").strip()
        except EOFError:
            return ""
