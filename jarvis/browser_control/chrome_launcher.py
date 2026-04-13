"""
chrome_launcher.py — Launch Chrome with a real user profile + remote-debug port,
or attach transparently to an already-running Chrome with the debug port open.

Design rules:
  - Never closes the user's existing browser session.
  - Handles 3 states:
      1. Chrome running WITH debug port  → attach directly (fastest)
      2. Chrome NOT running              → launch it, then attach
      3. Chrome running WITHOUT debug port → warn + exit cleanly
"""

import os
import platform
import socket
import subprocess
import time
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logger = logging.getLogger("browser_control.chrome_launcher")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ── Constants ─────────────────────────────────────────────────────────────────
CDP_PORT = int(os.getenv("CDP_PORT", "9222"))


def _default_chrome_path() -> str:
    """Return a platform-appropriate fallback Chrome executable path."""
    system = platform.system()
    if system == "Windows":
        return "C:/Program Files/Google/Chrome/Application/chrome.exe"
    elif system == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    else:
        return "/usr/bin/google-chrome"


def _chrome_process_exists() -> bool:
    """
    Check whether any Chrome process (without debug port) is running.
    Windows: uses 'tasklist'; Unix: uses 'ps'.
    """
    system = platform.system()
    try:
        if system == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "chrome.exe" in result.stdout.lower()
        else:
            result = subprocess.run(
                ["pgrep", "-x", "chrome"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
    except Exception:
        return False  # Can't determine → assume not running


# ── Exception ─────────────────────────────────────────────────────────────────

class ChromeLaunchError(Exception):
    """Raised when Chrome cannot be launched or the debug port never opens."""
    pass


# ── Main class ───────────────────────────────────────────────────────────────

class ChromeLauncher:
    """
    Manages attaching Playwright to a real Chrome browser via CDP.

    Typical usage:
        launcher = ChromeLauncher()
        browser, context, page = launcher.attach(playwright_instance)
    """

    def __init__(self):
        self.chrome_path: str = os.getenv("CHROME_PATH", "") or _default_chrome_path()
        self.profile_path: str = os.getenv(
            "CHROME_PROFILE_PATH",
            str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"),
        )
        self.profile_name: str = os.getenv("CHROME_PROFILE_NAME", "Default")
        self.cdp_port: int = CDP_PORT

    # ── Port / process checks ─────────────────────────────────────────────────

    def is_chrome_running(self) -> bool:
        """
        Return True if a Chrome instance is accepting CDP connections on
        localhost:{cdp_port}.  Uses a 1-second connect timeout.
        """
        try:
            with socket.create_connection(("localhost", self.cdp_port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            return False

    # ── Launch ────────────────────────────────────────────────────────────────

    def launch_chrome(self) -> None:
        """
        Start Chrome with the user's real profile and a remote-debugging port.

        Polls the debug port every 0.5 s for up to 15 s.
        Raises ChromeLaunchError if the port never opens.
        """
        args = [
            self.chrome_path,
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={self.profile_path}",
            f"--profile-directory={self.profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        logger.info(f"Launching Chrome: {' '.join(args)}")
        subprocess.Popen(args)

        # Wait for the debug port to open
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.is_chrome_running():
                logger.info(f"Chrome launched successfully — debug port {self.cdp_port} open")
                return
            time.sleep(0.5)

        raise ChromeLaunchError(
            f"Chrome debug port {self.cdp_port} did not open within 15 seconds.\n"
            f"  → Verify CHROME_PATH={self.chrome_path} is correct.\n"
            f"  → On Windows, close all Chrome windows first, then retry."
        )

    # ── Attach ────────────────────────────────────────────────────────────────

    def attach(self, playwright_instance):
        """
        Attach Playwright to the running (or newly launched) Chrome instance.

        Returns (Browser, BrowserContext, Page).

        Safety guard: if Chrome is running WITHOUT the debug port,
        prints a clear message and raises ChromeLaunchError rather than
        silently hanging.
        """
        if not self.is_chrome_running():
            # Chrome may be running without the debug port
            if _chrome_process_exists():
                raise ChromeLaunchError(
                    "Chrome is open WITHOUT the remote-debug port.\n"
                    "Please close Chrome completely and try again.\n"
                    "  JARVIS will relaunch Chrome with the debug port automatically."
                )
            # Chrome is not running at all → launch it
            self.launch_chrome()

        cdp_url = f"http://localhost:{self.cdp_port}"
        logger.info(f"Connecting to Chrome via CDP at {cdp_url}")

        browser = playwright_instance.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        logger.info(
            f"Attached to Chrome — {len(context.pages)} tab(s) open | "
            f"Active tab: {page.url}"
        )
        return browser, context, page

    # ── Tab helpers ───────────────────────────────────────────────────────────

    def get_all_tabs(self, context) -> list[dict]:
        """
        Return metadata for every open tab.

        Example output:
            [{"index": 0, "title": "Gmail", "url": "https://mail.google.com/..."}]
        """
        tabs = []
        for i, p in enumerate(context.pages):
            tabs.append({"index": i, "title": p.title(), "url": p.url})
        return tabs

    def switch_to_tab(self, context, index: int):
        """
        Switch focus to the tab at *index* and return the Page object.
        Raises IndexError if the index is out of range.
        """
        pages = context.pages
        if index < 0 or index >= len(pages):
            raise IndexError(
                f"Tab index {index} is out of range (0–{len(pages) - 1})."
            )
        page = pages[index]
        page.bring_to_front()
        logger.info(f"Switched to tab {index}: {page.url}")
        return page
