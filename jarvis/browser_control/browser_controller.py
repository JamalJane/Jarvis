"""
browser_controller.py — Main browser agent loop for JARVIS.

Combines:
  - ChromeLauncher (CDP attach)
  - DOMActions (fast DOM-based interactions)
  - GeminiClient (vision + text reasoning, 5-key rotation)

Gemini receives BOTH a browser screenshot AND the page's text content on
every step, making decisions far more accurate than vision-only approaches.
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Error as PlaywrightError

from ..screen_control.gemini_client import GeminiClient, AllKeysExhaustedError
from .chrome_launcher import ChromeLauncher, ChromeLaunchError
from .dom_actions import DOMActions

# ── Logging ───────────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logger = logging.getLogger("browser_control.browser_controller")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ── Known action names ────────────────────────────────────────────────────────
KNOWN_ACTIONS = {
    "goto", "click", "type", "press", "scroll", "wait",
    "back", "forward", "reload", "switch_tab", "read",
    "screenshot", "done", "failed",
}


class BrowserController:
    """
    Orchestrates a Gemini-driven browser automation loop.

    Usage:
        controller = BrowserController()
        controller.start()
        result = controller.run_task("go to gmail and find emails from Amazon")
        controller.stop()
    """

    def __init__(self):
        self.gemini = GeminiClient()          # 5-key rotation, reused from screen_control
        self.launcher = ChromeLauncher()
        self.dom: Optional[DOMActions] = None
        self.page = None
        self.browser = None
        self.context = None
        self.playwright = None
        self._session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Initialise Playwright and attach to Chrome."""
        self.playwright = sync_playwright().start()
        self.browser, self.context, self.page = self.launcher.attach(self.playwright)
        self.dom = DOMActions(self.page)
        logger.info("Browser controller ready — page: %s", self.page.url)

    def stop(self) -> None:
        """Cleanly shut down Playwright (does NOT close Chrome)."""
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                logger.warning("Error stopping Playwright: %s", e)
        logger.info("Browser controller stopped")

    # ── Public task runner ────────────────────────────────────────────────────

    def run_task(self, task_description: str, max_steps: int = 20) -> dict:
        """
        Run a Gemini-driven browser automation task.

        Returns a result dict:
            {
                "steps"     : list of step dicts,
                "final_url" : str,
                "success"   : bool,
            }
        """
        history: list[dict] = []

        for step in range(max_steps):
            # 1. Page info (text-based — fast, no screenshot yet)
            page_info = self.dom.get_page_info()

            # 2. Screenshot (browser viewport, faster than pyautogui)
            screenshot = self.dom.take_screenshot()

            # 3. Build prompt
            prompt = self._build_prompt(task_description, step, max_steps, history, page_info)

            # 4. Ask Gemini (vision + text)
            response = self.gemini.send_vision_prompt(screenshot, prompt)

            # 5. Parse the action JSON from Gemini's response
            action = self._parse_action(response)

            # 6. Log it
            self._log(step, action)

            # 7. Execute
            result = self._execute_action(action)

            # 8. Record in history
            history.append({"step": step, "action": action, "result": result})

            # Print live progress (visible in terminal)
            action_name = action.get("action", "?")
            print(f"  Step {step + 1:02d} | {action_name:<12} | {json.dumps(action)[:100]}")

            # 9. Terminal condition
            if action_name in ("done", "failed"):
                break

        final_action = history[-1]["action"].get("action", "") if history else ""
        return {
            "steps": history,
            "final_url": self.page.url,
            "success": final_action == "done",
        }

    # ── Action execution ──────────────────────────────────────────────────────

    def _execute_action(self, action: dict) -> dict:
        """Dispatch an action dict to the appropriate DOMActions method."""
        name = action.get("action", "screenshot")

        try:
            if name == "goto":
                title = self.dom.goto(action["url"])
                return {"status": "ok", "title": title}

            elif name == "click":
                ok = self.dom.click(
                    selector=action.get("selector"),
                    x=action.get("x"),
                    y=action.get("y"),
                )
                return {"status": "ok" if ok else "failed"}

            elif name == "type":
                ok = self.dom.type_text(
                    action["selector"],
                    action["text"],
                    clear_first=action.get("clear_first", True),
                )
                return {"status": "ok" if ok else "failed"}

            elif name == "press":
                self.dom.press_key(action["key"])
                return {"status": "ok"}

            elif name == "scroll":
                self.dom.scroll_page(
                    direction=action.get("direction", "down"),
                    amount=action.get("amount", 3),
                )
                return {"status": "ok"}

            elif name == "wait":
                found = self.dom.wait_for_element(
                    action["selector"],
                    timeout=action.get("timeout", 5_000),
                )
                return {"status": "ok" if found else "timeout"}

            elif name == "back":
                self.dom.go_back()
                return {"status": "ok"}

            elif name == "forward":
                self.dom.go_forward()
                return {"status": "ok"}

            elif name == "reload":
                self.dom.reload()
                return {"status": "ok"}

            elif name == "switch_tab":
                new_page = self.launcher.switch_to_tab(self.context, action["index"])
                self.page = new_page
                self.dom = DOMActions(self.page)
                return {"status": "ok", "url": self.page.url}

            elif name == "read":
                text = self.dom.get_text(action["selector"])
                return {"text": text or ""}

            elif name == "screenshot":
                # No-op: the loop will retake a screenshot next iteration
                return {"status": "ok"}

            elif name == "done":
                return {"status": "complete", "message": action.get("message", "")}

            elif name == "failed":
                return {"status": "failed", "reason": action.get("reason", "Unknown")}

            else:
                logger.warning("Unknown action: %s", name)
                return {"status": "unknown_action", "action": name}

        except PlaywrightError as e:
            logger.error("PlaywrightError during action '%s': %s", name, e)
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.error("Unexpected error during action '%s': %s", name, e)
            return {"status": "error", "error": str(e)}

    # ── Prompt building ───────────────────────────────────────────────────────

    def _build_prompt(
        self,
        task: str,
        step: int,
        max_steps: int,
        history: list[dict],
        page_info: dict,
    ) -> str:
        """Construct the Gemini system prompt for this step."""

        # Format history as bullet points (last 5 entries to stay concise)
        recent = history[-5:]
        if recent:
            history_lines = "\n".join(
                f"  [{h['step']}] {h['action'].get('action','?')}: "
                f"{json.dumps(h['action'])[:80]} → {json.dumps(h['result'])[:60]}"
                for h in recent
            )
        else:
            history_lines = "  (no actions yet)"

        return f"""You are a browser automation AI controlling a real Chrome browser.
The user is ALREADY LOGGED IN to their accounts. Do not attempt to log in
unless the task specifically requires it.

CURRENT TASK: {task}
STEP: {step + 1} of maximum {max_steps}

CURRENT PAGE INFO:
  URL: {page_info['url']}
  Title: {page_info['title']}
  Page text preview: {page_info['text_preview']}
  Input fields: {page_info['input_fields']}
  Buttons: {page_info['button_count']}

PREVIOUS ACTIONS:
{history_lines}

RULES:
1. Respond with ONLY a single JSON action. No explanation. Raw JSON only.
2. PREFER selector-based actions over coordinate clicks when possible.
   Selectors are more reliable than coordinates.
3. For selectors use: "#id", ".class", "button:has-text('Submit')",
   "input[placeholder='Search']", "[aria-label='Send']"
4. Only use x,y coordinates if no good selector exists.
5. The user is already logged in — don't navigate to login pages.
6. Read the page text preview carefully before deciding what to click.
7. After typing in a search box, press Enter or click the search button.
8. If a previous action failed, try a different selector or approach.
9. Never repeat the exact same failed action twice.
10. When the task is complete return done action immediately.

AVAILABLE ACTIONS (return exactly one):
{{"action": "goto", "url": "https://..."}}
{{"action": "click", "selector": "button:has-text('Send')"}}
{{"action": "click", "x": 450, "y": 320}}
{{"action": "type", "selector": "#search-input", "text": "hello", "clear_first": true}}
{{"action": "press", "key": "Enter"}}
{{"action": "scroll", "direction": "down", "amount": 3}}
{{"action": "wait", "selector": ".results", "timeout": 5000}}
{{"action": "back"}}
{{"action": "forward"}}
{{"action": "reload"}}
{{"action": "switch_tab", "index": 0}}
{{"action": "read", "selector": ".price"}}
{{"action": "screenshot"}}
{{"action": "done", "message": "Task complete: ..."}}
{{"action": "failed", "reason": "Could not find element after 3 attempts"}}

Screenshot of current browser state is attached.
What is your next action?"""

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_action(self, response: str) -> dict:
        """
        Extract a JSON action dict from Gemini's text response.

        Tries in order:
          1. Triple-backtick JSON block  (```json … ```)
          2. First raw JSON object       ({ … })
          3. Falls back to {"action": "screenshot"} (safe no-op)
        """
        if not response:
            logger.warning("Empty response from Gemini — defaulting to screenshot")
            return {"action": "screenshot"}

        # 1. Code-fenced JSON block
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                return self._validate_action(parsed)
            except json.JSONDecodeError:
                pass

        # 2. First bare JSON object
        raw_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if raw_match:
            try:
                parsed = json.loads(raw_match.group(0))
                return self._validate_action(parsed)
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse Gemini response as JSON: %r", response[:200])
        return {"action": "screenshot"}

    def _validate_action(self, action: dict) -> dict:
        """Ensure action dict has a known 'action' key; fall back if not."""
        if "action" not in action or action["action"] not in KNOWN_ACTIONS:
            logger.warning("Unknown or missing action field: %s", action)
            return {"action": "screenshot"}
        return action

    # ── Session logging ───────────────────────────────────────────────────────

    def _log(self, step: int, action: dict) -> None:
        """Append a step entry to the session log file."""
        log_path = Path("logs") / f"browser_session_{self._session_ts}.log"
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"Step {step:03d} | {action.get('action', '?'):12s} | "
                    f"{json.dumps(action)}\n"
                )
        except Exception as e:
            logger.warning("Could not write to session log: %s", e)
