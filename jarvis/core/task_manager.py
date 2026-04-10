import logging
import json
import time
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(Enum):
    CLICK = "click"
    TYPE = "type"
    PRESS = "press"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    SCREENSHOT = "screenshot"


@dataclass
class Action:
    type: ActionType
    params: dict
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        action_type = ActionType(data.get("action", "click"))
        return cls(
            type=action_type,
            params=data.get("params", {}),
            confidence=data.get("confidence", 1.0)
        )


@dataclass
class TaskResult:
    task_name: str
    actions_completed: int
    total_actions: int
    success: bool
    error: Optional[str] = None


class TaskManager:
    def __init__(self, api_manager, browser=None, automation=None, pinecone_store=None):
        self.api_manager = api_manager
        self.browser = browser
        self.automation = automation
        self.pinecone_store = pinecone_store
        self.task_history: List[dict] = []
        self.current_task: Optional[str] = None
        self.actions_completed = 0

    def execute_task(self, task_description: str) -> TaskResult:
        logger.info(f"Starting task: {task_description}")
        self.current_task = task_description
        self.actions_completed = 0

        try:
            actions_completed = self._run_task_loop(task_description)
            return TaskResult(
                task_name=task_description,
                actions_completed=actions_completed,
                total_actions=actions_completed,
                success=True
            )
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return TaskResult(
                task_name=task_description,
                actions_completed=self.actions_completed,
                total_actions=self.actions_completed,
                success=False,
                error=str(e)
            )

    def _run_task_loop(self, task_description: str) -> int:
        max_iterations = 50
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            screenshot_base64 = self._capture_context()

            prompt = f"""Task: {task_description}
Current progress: {self.actions_completed} actions completed

Respond with ONLY valid JSON, no other text:
{{"action": "done"}} if task is complete.
{{"action": "type", "params": {{"text": "what to type"}}}} to type text.
{{"action": "click", "params": {{"x": 100, "y": 200}}}} to click coordinates.
{{"action": "navigate", "params": {{"url": "https://..."}}}} to open a website.
{{"action": "screenshot", "params": {{"reason": "what to look for"}}}} to analyze screen."""

            response = self.api_manager.call_api(prompt, screenshot_base64)

            action = self._parse_action(response)
            if not action:
                logger.warning("Could not parse action, continuing...")
                continue

            if action.type == ActionType.NAVIGATE and "url" in action.params:
                if self.browser:
                    before_screenshot = self.browser.get_screenshot()
                    before_hash = self._hash_screenshot(before_screenshot) if before_screenshot else ""
                    self.browser.navigate(action.params["url"])
                    self.actions_completed += 1
                    after_screenshot = self.browser.get_screenshot()
                    after_hash = self._hash_screenshot(after_screenshot) if after_screenshot else ""
                    self._log_action(action, success=True, before_hash=before_hash, after_hash=after_hash)
                else:
                    self._log_action(action)
            elif action.type == ActionType.CLICK:
                x = action.params.get("x", 0)
                y = action.params.get("y", 0)
                before_screenshot = self._capture_before_action()
                before_hash = self._hash_screenshot(before_screenshot) if before_screenshot else ""
                if self.automation:
                    self.automation.click(x, y)
                self.actions_completed += 1
                after_screenshot = self._capture_after_action()
                after_hash = self._hash_screenshot(after_screenshot) if after_screenshot else ""
                self._log_action(action, success=True, before_hash=before_hash, after_hash=after_hash)
            elif action.type == ActionType.TYPE:
                text = action.params.get("text", "")
                before_screenshot = self._capture_before_action()
                before_hash = self._hash_screenshot(before_screenshot) if before_screenshot else ""
                if self.automation:
                    self.automation.type_text(text)
                self.actions_completed += 1
                after_screenshot = self._capture_after_action()
                after_hash = self._hash_screenshot(after_screenshot) if after_screenshot else ""
                self._log_action(action, success=True, before_hash=before_hash, after_hash=after_hash)
            elif action.type == ActionType.PRESS:
                key = action.params.get("key", "")
                before_screenshot = self._capture_before_action()
                before_hash = self._hash_screenshot(before_screenshot) if before_screenshot else ""
                if self.automation:
                    self.automation.press(key)
                self.actions_completed += 1
                after_screenshot = self._capture_after_action()
                after_hash = self._hash_screenshot(after_screenshot) if after_screenshot else ""
                self._log_action(action, success=True, before_hash=before_hash, after_hash=after_hash)
            elif action.type == ActionType.SCROLL:
                clicks = action.params.get("clicks", 0)
                before_screenshot = self._capture_before_action()
                before_hash = self._hash_screenshot(before_screenshot) if before_screenshot else ""
                if self.automation:
                    self.automation.scroll(clicks)
                self.actions_completed += 1
                after_screenshot = self._capture_after_action()
                after_hash = self._hash_screenshot(after_screenshot) if after_screenshot else ""
                self._log_action(action, success=True, before_hash=before_hash, after_hash=after_hash)
            elif action.type == ActionType.DONE or (hasattr(action, 'type') and action.type.value == "done"):
                logger.info("Task marked as done")
                break
            else:
                self._log_action(action)

        return self.actions_completed

    def _capture_context(self) -> Optional[str]:
        screenshot_bytes = None
        if self.browser and self.browser.is_running():
            try:
                screenshot_bytes = self.browser.get_screenshot()
            except Exception as e:
                logger.error(f"Failed to capture browser screenshot: {e}")
        
        # Fallback to desktop screen if browser screenshot failed or isn't running
        if not screenshot_bytes and self.automation:
            try:
                screenshot_bytes = self.automation.get_screenshot()
            except Exception as e:
                logger.error(f"Failed to capture desktop screenshot: {e}")

        if screenshot_bytes:
            import base64
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        return None

    def _parse_action(self, response: str) -> Optional[Action]:
        if not response or not response.strip():
            return None

        try:
            data = json.loads(response)
            return Action.from_dict(data)
        except json.JSONDecodeError:
            try:
                start = response.find('{')
                end = response.rfind('}') + 1
                if start != -1 and end > start:
                    data = json.loads(response[start:end])
                    return Action.from_dict(data)
            except:
                pass
            logger.warning(f"Could not parse action response: {response[:100]}...")
            return None

    def _log_action(self, action: Action, success: bool = True, before_hash: str = "", after_hash: str = ""):
        self.task_history.append({
            "action": action.type.value,
            "params": action.params,
            "confidence": action.confidence,
            "before_hash": before_hash,
            "after_hash": after_hash
        })
        logger.info(f"Action logged: {action.type.value}")
        
        if self.pinecone_store:
            from jarvis.memory.pinecone_store import ActionRecord
            target = str(action.params.get("url") or action.params.get("text") or action.params.get("x", ""))
            record = ActionRecord(
                action_type=action.type.value,
                action_target=target,
                before_dom_hash=before_hash,
                after_dom_hash=after_hash,
                success=success,
                task_type="browser" if action.type == ActionType.NAVIGATE else "os",
                timestamp=time.time(),
            )
            self.pinecone_store.store_action(record)

    def get_history(self) -> List[dict]:
        return self.task_history

    def clear_history(self):
        self.task_history = []

    def _capture_before_action(self) -> Optional[bytes]:
        try:
            if self.browser and self.browser.is_running():
                return self.browser.get_screenshot()
            if self.automation:
                return self.automation.get_screenshot()
        except Exception as e:
            logger.warning(f"Failed to capture before screenshot: {e}")
        return None

    def _capture_after_action(self) -> Optional[bytes]:
        import time
        time.sleep(0.5)
        try:
            if self.browser and self.browser.is_running():
                return self.browser.get_screenshot()
            if self.automation:
                return self.automation.get_screenshot()
        except Exception as e:
            logger.warning(f"Failed to capture after screenshot: {e}")
        return None

    def _hash_screenshot(self, screenshot_bytes: Optional[bytes]) -> str:
        if not screenshot_bytes:
            return ""
        import hashlib
        return hashlib.md5(screenshot_bytes).hexdigest()
