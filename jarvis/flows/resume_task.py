import logging
from pathlib import Path
from jarvis.utils.state_persistence import StateManager, TaskState
from jarvis.config.constants import RESUME_FILE
from jarvis.ui.display import Display

logger = logging.getLogger(__name__)


class ResumeHandler:
    def __init__(self, resume_file: Path = None):
        self.resume_file = resume_file or RESUME_FILE
        self.state_manager = StateManager(self.resume_file)

    def check_for_paused_task(self) -> bool:
        if self.state_manager.has_paused_task():
            state = self.state_manager.load_task_state()
            if state:
                Display.warning("⚠ Previous task paused:")
                Display.warning(f"{state.task_name} ({state.progress}/{state.total_actions} actions)")
                return True
        return False

    def pause_task(self, task_name: str, progress: int, total: int, context: dict = None, screenshots: list = None):
        state = TaskState(
            task_name=task_name,
            progress=progress,
            total_actions=total,
            context=context or {},
            screenshots=screenshots or []
        )
        self.state_manager.save_task_state(state)
        Display.status(f"Task paused at action {progress}/{total}")
        Display.status("Type 'resume' to continue")

    def resume_task(self) -> TaskState:
        state = self.state_manager.load_task_state()
        if not state:
            Display.error("No paused task found")
            return None
        self.state_manager.clear_task_state()
        return state

    def clear_paused_task(self):
        self.state_manager.clear_task_state()
