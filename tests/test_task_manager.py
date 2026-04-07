import pytest
from jarvis.core.automation import AutomationController
from jarvis.core.task_manager import TaskManager, ActionType, Action, TaskResult


def test_automation_controller_initializes():
    automation = AutomationController()
    assert automation is not None


def test_action_type_enum():
    assert ActionType.CLICK.value == "click"
    assert ActionType.TYPE.value == "type"
    assert ActionType.NAVIGATE.value == "navigate"


def test_action_from_dict():
    data = {"action": "click", "params": {"x": 100, "y": 200}, "confidence": 0.9}
    action = Action.from_dict(data)
    assert action.type == ActionType.CLICK
    assert action.params == {"x": 100, "y": 200}
    assert action.confidence == 0.9


def test_task_result():
    result = TaskResult(
        task_name="test task",
        actions_completed=5,
        total_actions=10,
        success=False,
        error="Test error"
    )
    assert result.task_name == "test task"
    assert result.actions_completed == 5
    assert result.success is False


def test_task_manager_initializes():
    manager = TaskManager(api_manager=None)
    assert manager.api_manager is None
    assert manager.browser is None
    assert manager.automation is None
    assert manager.actions_completed == 0


def test_task_manager_history():
    manager = TaskManager(api_manager=None)
    assert manager.get_history() == []
    manager._log_action(Action(ActionType.CLICK, {"x": 10, "y": 20}))
    assert len(manager.get_history()) == 1
    manager.clear_history()
    assert len(manager.get_history()) == 0
