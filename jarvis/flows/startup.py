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
    # Removed raw log generation because httpx/API debug logs were ruining the aesthetic user prompt.
    return "Core memory modules initialized and system processes ready."


def display_api_status(api_manager: APIManager):
    status = api_manager.get_status()
    for display_name, counts in status["status"].items():
        print(f"  {display_name}: {counts['remaining']}/{counts['total']} requests remaining")
