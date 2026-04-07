import logging
import json
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
    def __init__(self, api_manager, browser=None, automation=None):
        self.api_manager = api_manager
        self.browser = browser
        self.automation = automation
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

Return a JSON object with:
- "action": action type (click, type, press, scroll, navigate, wait, screenshot, done)
- "params": parameters for the action
- "confidence": confidence score (0-1)
- "reasoning": brief explanation

If task is complete, return {{"action": "done", "params": {{}}, "confidence": 1.0}}"""

            response = self.api_manager.call_api(prompt, screenshot_base64)

            action = self._parse_action(response)
            if not action:
                logger.warning("Could not parse action, continuing...")
                continue

            if action.type == ActionType.NAVIGATE and "url" in action.params:
                if self.browser:
                    self.browser.navigate(action.params["url"])
                    self.actions_completed += 1
            elif action.type == ActionType.CLICK:
                x = action.params.get("x", 0)
                y = action.params.get("y", 0)
                if self.automation:
                    self.automation.click(x, y)
                self.actions_completed += 1
            elif action.type == ActionType.TYPE:
                text = action.params.get("text", "")
                if self.automation:
                    self.automation.type_text(text)
                self.actions_completed += 1
            elif action.type == ActionType.PRESS:
                key = action.params.get("key", "")
                if self.automation:
                    self.automation.press(key)
                self.actions_completed += 1
            elif action.type == ActionType.SCROLL:
                clicks = action.params.get("clicks", 0)
                if self.automation:
                    self.automation.scroll(clicks)
                self.actions_completed += 1
            elif action.type == ActionType.DONE or (hasattr(action, 'type') and action.type.value == "done"):
                logger.info("Task marked as done")
                break

            self._log_action(action)

        return self.actions_completed

    def _capture_context(self) -> Optional[str]:
        if not self.browser:
            return None
        try:
            screenshot_bytes = self.browser.get_screenshot()
            if screenshot_bytes:
                import base64
                return base64.b64encode(screenshot_bytes).decode()
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
        return None

    def _parse_action(self, response: str) -> Optional[Action]:
        try:
            data = json.loads(response)
            return Action.from_dict(data)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse action response: {response[:100]}...")
            return None

    def _log_action(self, action: Action):
        self.task_history.append({
            "action": action.type.value,
            "params": action.params,
            "confidence": action.confidence
        })
        logger.info(f"Action logged: {action.type.value}")

    def get_history(self) -> List[dict]:
        return self.task_history

    def clear_history(self):
        self.task_history = []
