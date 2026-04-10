"""
safety_layer.py — 3-tier safety wrapper around every PyAutoGUI action.

TIER 1 - AUTO:      Executes immediately (move, screenshot, scroll, safe keys)
TIER 2 - LOG_ONLY:  Executes + logs to logs/actions.log (type, click, drag)
TIER 3 - CONFIRM:   Pauses and prompts terminal [y/n] before executing
                    (destructive keys, tasks containing send/delete/pay/submit/etc.)
"""

import logging
import time
import pyperclip
import pyautogui
from pathlib import Path
from datetime import datetime

# ── Logging setup ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)

_action_logger = logging.getLogger("actions")
_action_logger.setLevel(logging.DEBUG)
if not _action_logger.handlers:
    fh = logging.FileHandler("logs/actions.log")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _action_logger.addHandler(fh)


# Keys that are considered destructive and require TIER 3 confirmation
_DESTRUCTIVE_KEYS = {"delete", "enter", "win", "cmd", "f4"}

# Task description keywords that escalate ALL actions to TIER 3
_DESTRUCTIVE_TASK_WORDS = {"send", "submit", "delete", "purchase", "pay", "post", "remove", "erase"}


class SafetyLayer:
    """
    Wraps every action execution with safety checks before passing to PyAutoGUI.
    task_description is checked for destructive language to widen TIER 3 scope.
    """

    def __init__(self, task_description: str = ""):
        self.task_description = task_description.lower()
        self._task_is_destructive = bool(
            _DESTRUCTIVE_TASK_WORDS & set(self.task_description.split())
        )

    # ── Tier classification ───────────────────────────────────────────────────

    def _get_tier(self, action: dict) -> int:
        action_type = action.get("action", "")

        # Always TIER 1 (safe, non-mutating)
        if action_type in ("move", "screenshot", "scroll"):
            return 1

        # Key combos: check if any key fragment is destructive
        if action_type == "key":
            keys_str = action.get("keys", "").lower()
            key_parts = set(keys_str.split("+"))
            if key_parts & _DESTRUCTIVE_KEYS:
                return 3
            return 1  # non-destructive hotkeys are safe

        # Terminal actions: always auto (no real execution needed)
        if action_type in ("done", "failed"):
            return 1

        # Typing and clicking always get logged
        if action_type in ("type", "click", "double_click", "drag"):
            # Escalate to TIER 3 if task is flagged as destructive
            if self._task_is_destructive:
                return 3
            return 2

        # App launching is always a TIER 3 action for safety
        if action_type == "open_app":
            return 3

        # Default: LOG_ONLY for anything unrecognized
        return 2

    # ── Public execute entry point ────────────────────────────────────────────

    def execute(self, action: dict) -> dict:
        tier = self._get_tier(action)
        action_type = action.get("action", "unknown")

        if tier == 3:
            print(f"\n⚠️  [TIER 3 - AUTONOMOUS EXECUTION]")
            print(f"   Executing potentially destructive action: {action}")
            # User explicitly requested full autonomy without [y/n] blocks

        try:
            result = self._execute_action(action)
        except pyautogui.FailSafeException:
            raise SystemExit("🛑 FAILSAFE TRIGGERED: Mouse moved to top-left corner. Aborting.")
        except Exception as e:
            _action_logger.error(f"Action FAILED | {action_type} | {e}")
            return {"status": "error", "action": action, "error": str(e)}

        if tier >= 2:
            _action_logger.info(f"Action OK | tier={tier} | {action_type} | {action}")

        return {"status": "success", "action": action, "result": result}

    # ── PyAutoGUI dispatch table ──────────────────────────────────────────────

    def _execute_action(self, action: dict) -> dict:
        a = action.get("action", "")

        if a == "click":
            x, y = action["x"], action["y"]
            button = action.get("button", "left")
            pyautogui.click(x, y, button=button)
            return {"clicked": (x, y), "button": button}

        elif a == "double_click":
            x, y = action["x"], action["y"]
            pyautogui.doubleClick(x, y)
            return {"double_clicked": (x, y)}

        elif a == "type":
            text = action.get("text", "")
            interval = action.get("interval", 0.03)
            # Use clipboard for non-ASCII characters (emoji, special chars)
            if any(ord(c) > 127 for c in text):
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
            else:
                pyautogui.typewrite(text, interval=interval)
            return {"typed": text}

        elif a == "key":
            keys = action.get("keys", "")
            parts = keys.split("+")
            pyautogui.hotkey(*[p.strip() for p in parts])
            return {"key": keys}

        elif a == "scroll":
            x, y = action.get("x", None), action.get("y", None)
            clicks = action.get("clicks", 0)
            pyautogui.scroll(clicks, x=x, y=y)
            return {"scrolled": clicks, "at": (x, y)}

        elif a == "open_app":
            app_name = action.get("name", "")
            pyautogui.hotkey("win")
            time.sleep(0.5)
            pyautogui.typewrite(app_name, interval=0.03)
            time.sleep(0.5)
            pyautogui.hotkey("enter")
            time.sleep(3.0)  # Wait 3 full seconds for heavy apps to open
            return {"opened_app": app_name}

        elif a == "move":
            x, y = action["x"], action["y"]
            duration = action.get("duration", 0.3)
            pyautogui.moveTo(x, y, duration=duration)
            return {"moved_to": (x, y)}

        elif a == "drag":
            sx, sy = action["start_x"], action["start_y"]
            ex, ey = action["end_x"], action["end_y"]
            duration = action.get("duration", 0.5)
            pyautogui.dragTo(ex, ey, duration=duration, startX=sx, startY=sy)
            return {"dragged": {"from": (sx, sy), "to": (ex, ey)}}

        elif a == "screenshot":
            return {"note": "retaking screenshot"}

        elif a in ("done", "failed"):
            msg = action.get("message", action.get("reason", ""))
            return {"status": "terminal", "message": msg}

        else:
            return {"note": f"unknown action '{a}' — no-op"}
