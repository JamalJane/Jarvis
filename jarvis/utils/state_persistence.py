import json
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class TaskState:
    task_name: str
    progress: int
    total_actions: int
    context: dict = field(default_factory=dict)
    screenshots: List[str] = field(default_factory=list)

    def save(self, filepath: Path):
        with open(filepath, "w") as f:
            json.dump(asdict(self), f, indent=2)
        logger.info(f"Task state saved to {filepath}")

    @classmethod
    def load(cls, filepath: Path) -> Optional["TaskState"]:
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            logger.error(f"Failed to load task state: {e}")
            return None


class StateManager:
    def __init__(self, resume_file: Path):
        self.resume_file = resume_file

    def save_task_state(self, task_state: TaskState):
        task_state.save(self.resume_file)

    def load_task_state(self) -> Optional[TaskState]:
        return TaskState.load(self.resume_file)

    def has_paused_task(self) -> bool:
        return self.resume_file.exists()

    def clear_task_state(self):
        if self.resume_file.exists():
            self.resume_file.unlink()
            logger.info("Task state cleared")
