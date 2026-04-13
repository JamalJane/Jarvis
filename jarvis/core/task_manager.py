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
    DONE = "done"
    ANSWER = "answer"
    FAILED = "failed"
    # Google API actions — handled via google_services, NOT mouse/keyboard
    GOOGLE_SEND_EMAIL = "google_send_email"
    GOOGLE_CHECK_CALENDAR = "google_check_calendar"
    GOOGLE_CREATE_DOC = "google_create_doc"


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
    message: Optional[str] = None


class TaskManager:
    def __init__(self, api_manager, browser=None, automation=None, pinecone_store=None, google_services=None):
        self.api_manager = api_manager
        self.browser = browser
        self.automation = automation
        self.pinecone_store = pinecone_store
        self.google_services = google_services  # Gmail / Calendar / Docs
        self.task_history: List[dict] = []
        self.current_task: Optional[str] = None
        self.actions_completed = 0

    def execute_task(self, task_description: str, conversation_context: str = "") -> TaskResult:
        logger.info(f"Starting task: {task_description}")
        self.current_task = task_description
        self.actions_completed = 0

        try:
            actions_completed, final_message = self._run_task_loop(task_description, conversation_context)
            return TaskResult(
                task_name=task_description,
                actions_completed=actions_completed,
                total_actions=actions_completed,
                success=True,
                message=final_message
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

    def _run_task_loop(self, task_description: str, conversation_context: str = "") -> tuple[int, Optional[str]]:
        max_iterations = 50
        iterations = 0
        final_message = None

        while iterations < max_iterations:
            iterations += 1

            screenshot_base64 = self._capture_context()

            history_text = "\n".join(
                [f"- {h['action']} with params {h.get('params', {})}" 
                 for h in self.task_history[-self.actions_completed:]]
            ) if self.actions_completed > 0 else "No actions taken yet."

            # Build the prompt — advertise Google API actions when available
            google_actions_block = ""
            if self.google_services and self.google_services.is_authenticated():
                google_actions_block = """
‼️  GOOGLE API ACTIONS (always prefer these over opening apps or websites for email/calendar/docs tasks):
{{"action": "google_send_email", "params": {{"to": "recipient@email.com", "subject": "Subject", "body": "Body text"}}}}  — send an email via Gmail API.
{{"action": "google_check_calendar", "params": {{"max_results": 5}}}}  — list upcoming Google Calendar events.
{{"action": "google_create_doc", "params": {{"title": "Document title"}}}}  — create a new Google Doc.

DO NOT open Outlook, Chrome, or any desktop app for email/calendar/docs tasks. Use the google_* actions above."""

            context_block = f"Past Conversation Context:\n{conversation_context}\n" if conversation_context else ""
            prompt = f"""{context_block}Task: {task_description}
Current progress: {self.actions_completed} actions completed

Past actions taken for this task:
{history_text}
{google_actions_block}

CRITICAL DESKTOP RULES (only for tasks that are NOT email/calendar/docs):
- To open a Windows desktop app, emit a 'press' action with key 'win', wait for the next turn, emit a 'type' action with the app name, and finally 'press' enter.
- You MUST only execute ONE action per turn (e.g. only press win, don't combine with typing).

Respond with ONLY valid JSON. If the task is just a question or doesn't require any action, respond with:
{{"action": "answer", "params": {{"text": "your response here"}}}}

Otherwise respond with only one of these actions:
{{"action": "done"}} if task is complete.
{{"action": "type", "params": {{"text": "what to type"}}}} to type text.
{{"action": "click", "params": {{"x": 100, "y": 200}}}} to click coordinates.
{{"action": "press", "params": {{"key": "win"}}}} to press a key (e.g. win, enter, tab, esc).
{{"action": "scroll", "params": {{"clicks": 3}}}} to scroll.
{{"action": "navigate", "params": {{"url": "https://..."}}}} to open a website.
{{"action": "screenshot", "params": {{"reason": "what to look for"}}}} to analyze screen."""

            response = self.api_manager.call_api(prompt, screenshot_base64)

            action = self._parse_action(response)
            if not action:
                logger.warning("Could not parse action, continuing...")
                continue

            if action.type == ActionType.GOOGLE_SEND_EMAIL:
                to      = action.params.get("to", "")
                subject = action.params.get("subject", "")
                body    = action.params.get("body", "")
                if self.google_services and to:
                    try:
                        self.google_services.send_email(to, subject, body)
                        result_text = f"Email sent to {to} — '{subject}'"
                        logger.info(result_text)
                        print(f"\n✅ {result_text}\n")
                        self.actions_completed += 1
                        self._log_action(action, success=True)
                    except Exception as e:
                        logger.error(f"google_send_email failed: {e}")
                        print(f"\n❌ Failed to send email: {e}\n")
                        self._log_action(action, success=False)
                else:
                    print("\n❌ Google services not available or 'to' address missing.\n")
                    self._log_action(action, success=False)

            elif action.type == ActionType.GOOGLE_CHECK_CALENDAR:
                max_results = action.params.get("max_results", 5)
                if self.google_services:
                    try:
                        events = self.google_services.list_upcoming_events(max_results=max_results)
                        if not events:
                            output = "No upcoming events found on your Google Calendar."
                        else:
                            lines = []
                            for ev in events:
                                start = ev['start'].get('dateTime', ev['start'].get('date'))
                                lines.append(f"• {start}: {ev.get('summary', '(no title)')}")
                            output = "Upcoming events:\n" + "\n".join(lines)
                        logger.info(output)
                        print(f"\n{output}\n")
                        self.actions_completed += 1
                        self._log_action(action, success=True)
                    except Exception as e:
                        logger.error(f"google_check_calendar failed: {e}")
                        print(f"\n❌ Calendar error: {e}\n")
                        self._log_action(action, success=False)
                else:
                    print("\n❌ Google services not available.\n")
                    self._log_action(action, success=False)

            elif action.type == ActionType.GOOGLE_CREATE_DOC:
                title = action.params.get("title", "Untitled")
                if self.google_services:
                    try:
                        doc = self.google_services.create_doc(title)
                        doc_id  = doc.get('documentId')
                        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                        result_text = f"Created Google Doc '{title}'\n{doc_url}"
                        logger.info(result_text)
                        print(f"\n✅ {result_text}\n")
                        self.actions_completed += 1
                        self._log_action(action, success=True)
                    except Exception as e:
                        logger.error(f"google_create_doc failed: {e}")
                        print(f"\n❌ Failed to create doc: {e}\n")
                        self._log_action(action, success=False)
                else:
                    print("\n❌ Google services not available.\n")
                    self._log_action(action, success=False)

            elif action.type == ActionType.NAVIGATE and "url" in action.params:
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
            elif action.type == ActionType.ANSWER:
                answer_text = action.params.get("text", "")
                if answer_text:
                    logger.info(f"Answer: {answer_text}")
                    print(f"\n{answer_text}\n")
                    final_message = answer_text
                logger.info("Task marked as done (answer)")
                break
            else:
                self._log_action(action)

        return self.actions_completed, final_message

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
