import os
import logging
from jarvis.ui.display import Display
from ..config.api_manager import APIManager

logger = logging.getLogger(__name__)


def run_startup(api_manager: APIManager) -> str:
    username = os.getenv("USERNAME", "bashdakid0")

    summary = load_startup_summary()

    Display.greeting(username, summary)
    display_api_status(api_manager)
    Display.prompt()

    return username


def load_startup_summary() -> str:
    log_file = "logs/jarvis.log"
    if not os.path.exists(log_file):
        return "No recent activity"

    try:
        with open(log_file, "r") as f:
            lines = f.readlines()[-10:]
        return "\n".join(lines) if lines else "No recent activity"
    except Exception:
        return "No recent activity"


def display_api_status(api_manager: APIManager):
    status = api_manager.get_status()
    for display_name, counts in status["status"].items():
        print(f"  {display_name}: {counts['remaining']}/{counts['total']} requests remaining")
