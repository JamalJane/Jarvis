"""
browser_control — Playwright CDP-attach browser automation module for JARVIS.
Controls the user's real Chrome browser (logged-in profile, real cookies).
"""

from .chrome_launcher import ChromeLauncher, ChromeLaunchError
from .dom_actions import DOMActions
from .browser_controller import BrowserController

__all__ = ["ChromeLauncher", "ChromeLaunchError", "DOMActions", "BrowserController"]
