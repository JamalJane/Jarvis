import logging
import sys
import os
from pathlib import Path
from jarvis.config.api_manager import APIManager
from jarvis.core.voice import VoiceIO
from jarvis.core.browser import BrowserController
from jarvis.core.automation import AutomationController
from jarvis.core.task_manager import TaskManager
from jarvis.flows.startup import run_startup
from jarvis.flows.voice_query import run_voice_query
from jarvis.flows.blacklist_action import BlacklistHandler
from jarvis.flows.resume_task import ResumeHandler
from jarvis.flows.help_command import handle_help_command
from jarvis.memory.pinecone_store import PineconeStore
from jarvis.memory.prediction import PredictionEngine
from jarvis.memory.context_selector import ContextSelector
from jarvis.ui.display import Display

logger = logging.getLogger(__name__)


class Jarvis:
    def __init__(self):
        self.api_manager = APIManager()
        self.voice = VoiceIO()
        self.browser = BrowserController()
        self.automation = AutomationController()
        self.blacklist_handler = BlacklistHandler()
        self.resume_handler = ResumeHandler()

        pinecone_key = os.getenv("PINECONE_API_KEY", "")
        pinecone = PineconeStore(api_key=pinecone_key)
        self.prediction_engine = PredictionEngine(pinecone)
        self.context_selector = ContextSelector(self.prediction_engine)

        self.task_manager = TaskManager(
            api_manager=self.api_manager,
            browser=self.browser,
            automation=self.automation
        )

    def run(self):
        username = run_startup(self.api_manager)

        if self.resume_handler.check_for_paused_task():
            try:
                response = input("Resume? (y/n): ")
                if response.lower() == "y":
                    state = self.resume_handler.resume_task()
                    if state:
                        self._execute_resumed_task(state)
            except EOFError:
                pass

        self._main_loop()

    def _main_loop(self):
        while True:
            Display.prompt()
            try:
                user_input = sys.stdin.readline().strip()
            except EOFError:
                break

            if not user_input:
                user_input = self._handle_voice_input()
                if not user_input:
                    continue

            if handle_help_command(user_input):
                continue

            if user_input.lower() == "resume":
                state = self.resume_handler.resume_task()
                if state:
                    self._execute_resumed_task(state)
                continue

            if user_input.lower() in ["done", "stop"]:
                Display.status("Task ended")
                continue

            if user_input.startswith("type "):
                query = user_input[5:]
            else:
                query = user_input

            if query:
                self._execute_query(query)

    def _handle_voice_input(self) -> str:
        Display.status("Voice mode active")
        return run_voice_query()

    def _execute_query(self, query: str):
        Display.status(f"Starting task: {query}")

        try:
            if not self.browser.is_running():
                if not self.browser.start():
                    Display.error("Failed to start browser")
                    return

            self.browser.navigate("https://www.google.com")

            result = self.task_manager.execute_task(query)
            if result.success:
                Display.success(f"Task completed: {result.actions_completed} actions")
            else:
                Display.error(f"Task failed: {result.error}")

        except Exception as e:
            logger.error(f"Task failed: {e}")
            Display.error(f"Task failed: {e}")

    def _execute_resumed_task(self, state):
        logger.info(f"Resuming task: {state.task_name}")
        Display.status(f"Resuming: {state.task_name}")
        self._execute_query(state.task_name)

    def cleanup(self):
        if self.browser:
            self.browser.close()
        Display.status("JARVIS shutting down...")
