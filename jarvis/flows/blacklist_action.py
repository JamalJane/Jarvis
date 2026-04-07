import logging
from jarvis.config.blacklist import BlacklistChecker
from jarvis.ui.display import Display

logger = logging.getLogger(__name__)


class BlacklistHandler:
    def __init__(self):
        self.checker = BlacklistChecker()

    def check_and_handle(self, action_description: str, execute_func) -> bool:
        if not self.checker.is_blacklisted(action_description):
            return execute_func()

        Display.warning("⚠ WARNING: Blacklisted action detected")
        Display.warning(f"Action: {action_description}")

        try:
            response = input("Proceed? (y/n): ")
        except EOFError:
            response = "n"

        if response.lower() == "y":
            logger.info(f"User approved blacklisted action: {action_description}")
            return execute_func()

        Display.status("Action skipped")
        return False

    def is_blocked(self, action_description: str) -> bool:
        return self.checker.is_blacklisted(action_description)
