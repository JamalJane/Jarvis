"""
screen_controller.py — Main Gemini Vision automation loop.

Captures screenshots, scales AI coordinates from 1280x720 to real screen size,
sends to Gemini, parses JSON actions, executes via SafetyLayer, tracks history.
Also provides find_on_screen() OpenCV template matching fallback.
"""

import json
import logging
import re
import time
import cv2
import numpy as np
import pyautogui
from datetime import datetime
from pathlib import Path
from PIL import Image

from jarvis.screen_control.gemini_client import GeminiClient
from jarvis.screen_control.safety_layer import SafetyLayer

# ── PyAutoGUI global config ───────────────────────────────────────────────────
pyautogui.FAILSAFE = True   # Move mouse to top-left corner = emergency abort
pyautogui.PAUSE = 0.05      # 50ms pause between actions

# ── Logging setup ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)

_ctrl_logger = logging.getLogger("screen_controller")
_ctrl_logger.setLevel(logging.DEBUG)
if not _ctrl_logger.handlers:
    fh = logging.FileHandler("logs/actions.log")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _ctrl_logger.addHandler(fh)

# Known valid action names
_VALID_ACTIONS = {
    "click", "double_click", "type", "key", "scroll",
    "move", "drag", "screenshot", "open_app", "done", "failed"
}


class ScreenController:
    """
    Core automation controller.
    - Captures screenshots at 1280x720.
    - Scales AI-returned coordinates to real screen dimensions.
    - Runs the Gemini Vision agent loop up to max_steps.
    - Delegates execution to SafetyLayer.
    """

    AI_W = 1280
    AI_H = 720

    def __init__(self):
        self.gemini = GeminiClient()
        # Real screen dimensions — captured once and reused for scaling
        self.real_w, self.real_h = pyautogui.size()
        self.scale_x = self.real_w / self.AI_W
        self.scale_y = self.real_h / self.AI_H

        _ctrl_logger.info(
            f"ScreenController init | screen={self.real_w}x{self.real_h} "
            f"| scale_x={self.scale_x:.4f} scale_y={self.scale_y:.4f}"
        )

        try:
            from jarvis.memory.pinecone_store import PineconeStore
            self.memory = PineconeStore()
            _ctrl_logger.info("Pinecone memory connected to ScreenController.")
        except ImportError:
            self.memory = None
            _ctrl_logger.warning("PineconeStore not found. Running without memory.")

    # ── Coordinate scaling (CRITICAL) ─────────────────────────────────────────

    def scale_coords(self, ai_x: int, ai_y: int) -> tuple[int, int]:
        """
        Convert AI-space coordinates (1280x720) to real screen coordinates.
        Without this, clicks land in the wrong spot on any non-1280x720 display.

        real_w, real_h = pyautogui.size()
        scale_x = real_w / 1280
        scale_y = real_h / 720
        real_x = int(ai_x * scale_x)
        real_y = int(ai_y * scale_y)
        """
        real_x = int(ai_x * self.scale_x)
        real_y = int(ai_y * self.scale_y)
        return real_x, real_y

    def _apply_scaling_to_action(self, action: dict) -> dict:
        """
        Mutate coordinate fields in action from AI space → real screen space.
        Returns a new dict to avoid modifying the original.
        """
        a = dict(action)
        atype = a.get("action", "")

        if atype in ("click", "double_click", "move", "scroll"):
            if "x" in a and "y" in a:
                a["x"], a["y"] = self.scale_coords(a["x"], a["y"])

        elif atype == "drag":
            if "start_x" in a:
                a["start_x"], a["start_y"] = self.scale_coords(a["start_x"], a["start_y"])
            if "end_x" in a:
                a["end_x"], a["end_y"] = self.scale_coords(a["end_x"], a["end_y"])

        return a

    # ── Screenshot ────────────────────────────────────────────────────────────

    def take_screenshot(self) -> Image.Image:
        """
        Capture the full screen, resize to 1280x720 for Gemini,
        and save a copy to logs/last_screenshot.png for debugging.
        """
        img = pyautogui.screenshot()
        img_resized = img.resize((self.AI_W, self.AI_H), Image.LANCZOS)
        img_resized.save("logs/last_screenshot.png")
        return img_resized

    # ── Prompt builder ────────────────────────────────────────────────────────

    def build_prompt(self, task_description: str, step: int, history: list, past_memories: list = None) -> str:
        if history:
            history_lines = "\n".join(
                f"  Step {h['step']}: {h['action'].get('action','?')} "
                f"→ {h.get('result', {}).get('status', '?')}"
                for h in history[-8:]  # last 8 steps to keep context tight
            )
        else:
            history_lines = "  (none yet)"

        memory_section = ""
        if past_memories:
            memory_section = "\nRELEVANT PAST MEMORIES:\n"
            for m in past_memories:
                m_data = m.get("metadata", {})
                memory_section += f"- {m_data.get('action_type')}: {m_data.get('action_target')} (Success: {m_data.get('success')})\n"

        return f"""You are a desktop automation AI controlling a real Windows/Mac/Linux computer screen.
You can SEE the current screenshot and must decide the NEXT SINGLE ACTION to take.

CURRENT TASK: {task_description}
STEP: {step} 
PREVIOUS ACTIONS:
{history_lines}{memory_section}

RULES:
1. Respond with ONLY a single JSON action object. No explanation. No markdown. Just raw JSON.
2. Coordinates are in 1280x720 space. Be precise — look carefully at the screenshot.
3. If you see a text field, click it BEFORE typing.
4. If an action didn't work, try a different approach.
5. If the task is complete, return {{"action": "done", "message": "..."}}
6. If you are stuck after multiple retries, return {{"action": "failed", "reason": "..."}}
7. Never repeat the exact same failed action twice in a row.
8. For URLs: click the address bar (ctrl+l), then type the URL, then press enter.
9. For typing non-standard characters: use the clipboard (the system will handle it).
10. Always verify the previous action worked before proceeding.
11. NEVER click the taskbar (the bar of icons at the bottom of the screen). To open OR switch to any application, you MUST use the open windows mechanic exactly like this: {{"action": "open_app", "name": "app_name"}}

AVAILABLE ACTIONS (return exactly one):
{{"action": "click", "x": int, "y": int, "button": "left|right|middle"}}
{{"action": "double_click", "x": int, "y": int}}
{{"action": "type", "text": "string", "interval": 0.03}}
{{"action": "key", "keys": "ctrl+c"}}
{{"action": "scroll", "x": int, "y": int, "clicks": int}}
{{"action": "move", "x": int, "y": int, "duration": float}}
{{"action": "drag", "start_x": int, "start_y": int, "end_x": int, "end_y": int, "duration": float}}
{{"action": "open_app", "name": "string"}}
{{"action": "screenshot"}}
{{"action": "done", "message": "string"}}
{{"action": "failed", "reason": "string"}}

Current screenshot is attached. What is your next action?"""

    # ── JSON parser ───────────────────────────────────────────────────────────

    def parse_action(self, response_text: str) -> dict:
        """
        Extract a JSON action from Gemini's response.
        Handles ```json fenced blocks and raw JSON objects.
        Falls back to screenshot action on any parse failure.
        """
        # Try fenced code block first
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        raw_match = re.search(r"\{.*\}", response_text, re.DOTALL)

        json_str = None
        if fence_match:
            json_str = fence_match.group(1)
        elif raw_match:
            json_str = raw_match.group(0)

        if json_str:
            try:
                action = json.loads(json_str)
                if action.get("action") in _VALID_ACTIONS:
                    return action
                else:
                    _ctrl_logger.warning(f"Unknown action type in response: {action}")
            except json.JSONDecodeError as e:
                _ctrl_logger.warning(f"JSON parse error: {e} | raw: {response_text[:200]}")

        _ctrl_logger.warning(f"Could not parse action from response, retaking screenshot. Raw: {response_text[:200]}")
        return {"action": "screenshot"}

    # ── Log action ────────────────────────────────────────────────────────────

    def log_action(self, step: int, action: dict, session_log: logging.Logger = None):
        msg = f"Step {step:02d} | action={action.get('action')} | {action}"
        _ctrl_logger.info(msg)
        if session_log:
            session_log.info(msg)

    # ── OpenCV template match fallback ────────────────────────────────────────

    def find_on_screen(self, template, threshold: float = 0.8):
        """
        Find a template image on the real (unscaled) screen using OpenCV.
        template: file path (str/Path) or PIL Image
        Returns (center_x, center_y) in REAL screen coordinates, or None.
        """
        # Capture full-res screenshot
        screen_pil = pyautogui.screenshot()
        screen_np = cv2.cvtColor(np.array(screen_pil), cv2.COLOR_RGB2BGR)

        if isinstance(template, (str, Path)):
            tmpl_np = cv2.imread(str(template))
        else:
            tmpl_np = cv2.cvtColor(np.array(template), cv2.COLOR_RGB2BGR)

        if tmpl_np is None:
            _ctrl_logger.error("find_on_screen: template image could not be loaded")
            return None

        result = cv2.matchTemplate(screen_np, tmpl_np, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = tmpl_np.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            _ctrl_logger.info(f"find_on_screen: match confidence={max_val:.3f} at ({center_x}, {center_y})")
            return center_x, center_y

        _ctrl_logger.info(f"find_on_screen: no match above threshold {threshold} (best={max_val:.3f})")
        return None

    # ── Main agent loop ───────────────────────────────────────────────────────

    def run_task(self, task_description: str) -> list:
        """
        Run the Gemini Vision agent loop indefinitely until task is done or failed.
        Returns the full history list of steps.
        """
        # Session logger
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_log = logging.getLogger(f"session_{session_ts}")
        session_log.setLevel(logging.DEBUG)
        sfh = logging.FileHandler(f"logs/session_{session_ts}.log")
        sfh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        session_log.addHandler(sfh)

        session_log.info(f"=== NEW TASK: {task_description} ===")

        # Pull past memories if available
        past_memories = None
        if self.memory:
            try:
                past_memories = self.memory.query_similar(action_type="task", target=task_description, top_k=3)
            except Exception as e:
                session_log.warning(f"Failed to query Pinecone: {e}")

        safety = SafetyLayer(task_description)
        history: list[dict] = []
        step = 0

        while True:
            print(f"\n🔍 Step {step + 1} — capturing screen...")

            # 1. Take screenshot (resized to 1280x720)
            screenshot = self.take_screenshot()

            # 2. Build prompt
            prompt = self.build_prompt(task_description, step, history, past_memories)

            # 3. Send to Gemini Vision
            try:
                response = self.gemini.send_vision_prompt(screenshot, prompt)
            except Exception as e:
                session_log.error(f"Gemini call failed at step {step}: {e}")
                print(f"❌ Gemini error: {e}")
                break

            session_log.debug(f"Gemini raw response: {response[:300]}")

            # 4. Parse JSON action
            action = self.parse_action(response)
            print(f"🤖 AI action: {action}")

            # 5. Log action (BEFORE scaling — log AI-space coords for traceability)
            self.log_action(step, action, session_log)

            # 6. Scale coordinates from AI space → real screen space
            scaled_action = self._apply_scaling_to_action(action)

            # 7. Execute through safety layer
            result = safety.execute(scaled_action)
            print(f"✅ Result: {result.get('status')} | {result.get('result', '')}")

            # 8. Track history
            history.append({"step": step, "action": action, "result": result})

            # 9. Terminal conditions
            if action.get("action") in ("done", "failed"):
                session_log.info(f"Terminal action '{action['action']}' at step {step}. Stopping.")
                
                # Store final outcome in Pinecone
                if self.memory:
                    try:
                        from jarvis.memory.pinecone_store import ActionRecord
                        record = ActionRecord(
                            action_type="task",
                            action_target=task_description,
                            success=(action.get("action") == "done"),
                            task_type="screen_control",
                            execution_duration=step * 2.0  # approximate time
                        )
                        self.memory.store_action(record)
                    except Exception as e:
                        session_log.warning(f"Failed to store memory: {e}")
                        
                break

            # Buffer to let the UI animations finish, pages load, and apps fully render
            # before taking the next screenshot.
            time.sleep(2.5)
            step += 1

        session_log.info(f"=== TASK ENDED after {step + 1} step(s) ===")
        return history
