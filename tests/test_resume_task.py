import pytest
from pathlib import Path
import tempfile
from jarvis.utils.state_persistence import TaskState, StateManager
from jarvis.flows.resume_task import ResumeHandler


def test_task_state_creation():
    state = TaskState(
        task_name="test task",
        progress=5,
        total_actions=10
    )
    assert state.task_name == "test task"
    assert state.progress == 5
    assert state.total_actions == 10


def test_task_state_save_and_load():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = Path(f.name)

    try:
        state = TaskState(
            task_name="save test",
            progress=3,
            total_actions=7
        )
        state.save(temp_file)

        loaded = TaskState.load(temp_file)
        assert loaded is not None
        assert loaded.task_name == "save test"
        assert loaded.progress == 3
        assert loaded.total_actions == 7
    finally:
        if temp_file.exists():
            temp_file.unlink()


def test_state_manager_has_paused_task():
    temp_file = Path(tempfile.mktemp(suffix='.json'))

    try:
        manager = StateManager(temp_file)
        assert manager.has_paused_task() is False

        state = TaskState("test", 1, 5)
        manager.save_task_state(state)
        assert manager.has_paused_task() is True

        manager.clear_task_state()
        assert manager.has_paused_task() is False
    finally:
        if temp_file.exists():
            temp_file.unlink()


def test_resume_handler_initializes():
    handler = ResumeHandler()
    assert handler.state_manager is not None


def test_resume_handler_with_custom_file():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        temp_file = Path(f.name)

    try:
        handler = ResumeHandler(temp_file)
        assert handler.resume_file == temp_file
    finally:
        if temp_file.exists():
            temp_file.unlink()
