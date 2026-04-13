# JARVIS TUI Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Build a Textual-based terminal UI for JARVIS with 3-panel layout showing real-time task progress, agent logs, and status.

**Architecture:** Create new `jarvis/lib/` module exposing core functionality, then build TUI on top using Textual. Existing core modules stay unchanged - TUI imports from library.

**Tech Stack:** Python `textual` (TUI framework), `rich` (colors/logging), existing JARVIS core (`api_manager`, `task_manager`, `automation`).

---

## File Structure

```
jarvis/
  lib/
    __init__.py         # NEW: AgentLib, StepLog, TaskState, SafetyTier
  ui/
    textual_app.py       # NEW: Main TUI app with all panels
```

---

## Task 1: Create `jarvis/lib/` Module

**Files:**
- Create: `jarvis/lib/__init__.py`

- [ ] **Step 1: Create jarvis/lib/ directory and __init__.py**

```python
"""JARVIS Library - Core functionality exposed for TUI."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


class SafetyTier(Enum):
    """Safety levels for action execution."""
    AUTO = "auto"      # Execute without prompt
    LOG = "log"        # Log only, require approval
    CONFIRM = "confirm" # Explicit user confirmation


@dataclass
class StepLog:
    """Single step execution log entry."""
    step_number: int
    action_type: str
    params: dict
    status: str  # "success" | "running" | "failed" | "info"
    result: str = ""


@dataclass
class TaskState:
    """Current task execution state."""
    task_name: str
    status: str  # "idle" | "running" | "paused" | "complete" | "failed"
    current_step: int
    total_steps: int
    last_screenshot_path: str
    safety_tier: SafetyTier
    error: Optional[str] = None


class AgentLib:
    """Main library class wrapping JARVIS core functionality."""
    
    def __init__(self, on_step: Callable[[StepLog], None] = None):
        """Initialize with optional step callback."""
        from jarvis.config.api_manager import APIManager
        from jarvis.core.task_manager import TaskManager
        from jarvis.core.automation import AutomationController
        from jarvis.memory.pinecone_store import PineconeStore
        import os
        
        self.on_step = on_step
        self._paused = False
        self._stopped = False
        
        # Initialize core components
        self.api_manager = APIManager()
        self.automation = AutomationController()
        
        pinecone_key = os.getenv("PINECONE_API_KEY", "")
        self.pinecone_store = PineconeStore(api_key=pinecone_key) if pinecone_key else None
        
        self.task_manager = TaskManager(
            api_manager=self.api_manager,
            automation=self.automation,
            pinecone_store=self.pinecone_store
        )
        
        self._task_state: Optional[TaskState] = None
        self._step_logs: list[StepLog] = []
    
    def run_task(self, task_name: str) -> TaskState:
        """Run task in background. Returns initial state."""
        self._task_state = TaskState(
            task_name=task_name,
            status="running",
            current_step=0,
            total_steps=0,
            last_screenshot_path="",
            safety_tier=SafetyTier.AUTO
        )
        self._step_logs = []
        self._paused = False
        self._stopped = False
        return self._task_state
    
    def pause(self):
        """Pause after current step completes."""
        self._paused = True
    
    def resume(self):
        """Resume from pause."""
        self._paused = False
    
    def abort(self):
        """Stop immediately, move mouse to 0,0."""
        import pyautogui
        pyautogui.moveTo(0, 0)
        self._stopped = True
        if self._task_state:
            self._task_state.status = "failed"
            self._task_state.error = "Aborted by user"
    
    def get_api_status(self) -> dict:
        """Return key status for header display."""
        full_status = self.api_manager.get_status()
        current_idx = full_status.get("current_key", "none")
        if current_idx.startswith("GEMINI_KEY_"):
            num = current_idx.replace("GEMINI_KEY_", "")
            return {"current": int(num), "total": len(self.api_manager.keys)}
        return {"current": 1, "total": len(self.api_manager.keys)}
    
    def get_key_status_full(self) -> dict:
        """Detailed key status for status panel."""
        status = self.api_manager.get_status()
        result = {}
        for key, info in status.get("status", {}).display_name = key
            result[display_name] = {
                "used": info.get("used", 0),
                "remaining": info.get("remaining", 0),
                "failed": info.get("failed", False)
            }
        return result
    
    def get_step_logs(self) -> list[StepLog]:
        """Return all step logs."""
        return self._step_logs.copy()
    
    def get_task_state(self) -> Optional[TaskState]:
        """Return current task state."""
        return self._task_state
    
    def is_paused(self) -> bool:
        return self._paused
    
    def is_stopped(self) -> bool:
        return self._stopped
```

- [ ] **Step 2: Verify file created**

Run: `python -c "from jarvis.lib import AgentLib, StepLog, TaskState, SafetyTier; print('OK')"`
Expected: OK

- [ ] **Step 3: Add textual to requirements**

Run: `pip install textual` (already in textual>=0.1.0 but check)

Add to requirements.txt:
```
textual>=0.1.0
```

- [ ] **Step 4: Commit**

---

## Task 2: Create Main TUI Application

**Files:**
- Create: `jarvis/ui/textual_app.py`

- [ ] **Step 1: Write textual_app.py with full UI**

```python
"""JARVIS Textual TUI Application."""

import asyncio
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Static, Button, Input, Log, Label
from textual.reactive import reactive
from textual import work

from jarvis.lib import AgentLib, StepLog, TaskState, SafetyTier


# Colors (matching spec)
BG = "#0d1117"
PANEL_BG = "#161b22"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
GREEN = "#00ff88"
YELLOW = "#ffcc00"
RED = "#ff4444"
BLUE = "#4499ff"
BORDER = "#30363d"


class JarvisApp(App):
    """JARVIS Terminal UI Application."""
    
    CSS = f"""
    Screen {{
        background: {BG};
    }}
    
    #header-bar {{
        dock: top;
        height: 1;
        background: {PANEL_BG};
        color: {TEXT_PRIMARY};
    }}
    
    #main-container {{
        height: 100%;
    }}
    
    #left-panel {{
        width: 40%;
        background: {PANEL_BG};
        border-right: solid {BORDER};
    }}
    
    #right-panel {{
        width: 60%;
        background: {PANEL_BG};
    }}
    
    #log-view {{
        height: 100%;
        background: {PANEL_BG};
    }}
    
    .status-ok {{
        text: {GREEN};
    }}
    .status-running {{
        text: {YELLOW};
    }}
    .status-failed {{
        text: {RED};
    }}
    .status-info {{
        text: {BLUE};
    }}
    
    #input-bar {{
        dock: bottom;
        height: 3;
        background: {PANEL_BG};
    }}
    
    #task-input {{
        width: 60%;
    }}
    
    .button-send {{
        background: {GREEN};
        color: {BG};
    }}
    .button-abort {{
        background: {RED};
        color: {TEXT_PRIMARY};
    }}
    .button-pause {{
        background: {YELLOW};
        color: {BG};
    }}
    
    Static {{
        color: {TEXT_PRIMARY};
    }}
    
    .label-secondary {{
        color: {TEXT_SECONDARY};
    }}
    """
    
    # Reactive state
    task_name: str = ""
    status: str = "idle"
    current_step: int = 0
    total_steps: int = 0
    active_key: int = 1
    total_keys: int = 4
    latest_action: str = ""
    screenshot_path: str = ""
    safety_tier: str = "AUTO"
    paused: bool = False
    
    def __init__(self):
        super().__init__()
        self.agent = AgentLib(on_step=self._on_step)
        self._step_counter = 0
    
    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header(show_clock=False)
        
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Static("AGENT LOG", classes="label-secondary")
                yield Log(id="log-view", auto_scroll=True)
            
            with Vertical(id="right-panel"):
                yield Static("STATUS PANEL", classes="label-secondary")
                yield Static("Current Action:", classes="label-secondary")
                yield Static("", id="current-action")
                yield Static("Screenshot:", classes="label-secondary")
                yield Static("", id="screenshot-path")
                yield Static("Progress:", classes="label-secondary")
                yield Static("Step 0 / 0", id="progress")
                yield Static("API Keys:", classes="label-secondary")
                yield Static("", id="key-status")
                yield Static("Safety:", classes="label-secondary")
                yield Static("AUTO", id="safety-tier")
        
        with Horizontal(id="input-bar"):
            yield Input(placeholder="Enter task...", id="task-input")
            yield Button("SEND", id="btn-send", variant="primary")
            yield Button("ABORT", id="btn-abort", variant="error")
            yield Button("PAUSE", id="btn-pause", variant="warning")
    
    def _on_step(self, step: StepLog):
        """Handle step completion callback."""
        self._step_counter += 1
        self.current_step = step.step_number
        
        # Update log
        log = self.query_one("#log-view", Log)
        icon = {"success": "✓", "running": "⟳", "failed": "✗", "info": "📷"}.get(step.status, "?")
        color_class = {
            "success": "status-ok",
            "running": "status-running", 
            "failed": "status-failed",
            "info": "status-info"
        }.get(step.status, "")
        
        params_str = str(step.params) if step.params else ""
        log.write_line(f"Step {step.step_number}: {step.action_type} {params_str} [{icon}]")
        
        # Update status panel
        self.query_one("#current-action", Static).update(f"{step.action_type} {params_str}")
    
    def on_mount(self) -> None:
        """Initialize on mount."""
        self.title = "JARVIS v1.0"
        self.sub_title = "[● ONLINE]"
        self._update_key_display()
    
    def _update_key_display(self):
        """Update key status display."""
        key_status = self.agent.get_key_status_full()
        lines = []
        for i, (name, info) in enumerate(key_status.items(), 1):
            if info.get("failed"):
                status_text = "FAIL"
            elif i == self.active_key:
                status_text = "ACTIVE"
            else:
                status_text = f"OK ({info.get('remaining', 0)})"
            lines.append(f"Key {i}: {status_text}")
        self.query_one("#key-status", Static).update("\n".join(lines))
    
    @work(exclusive=True)
    async def run_task_async(self, task_name: str):
        """Run task asynchronously."""
        self.status = "running"
        self.task_name = task_name
        
        log = self.query_one("#log-view", Log)
        log.write_line(f"[Starting task: {task_name}]")
        
        self.agent.run_task(task_name)
        
        # Mock step execution for demonstration
        step_types = ["CLICK", "TYPE", "PRESS", "SCROLL", "SCREENSHOT"]
        for i in range(1, 6):
            if self.agent.is_stopped():
                break
            
            self._step_counter = i
            self.current_step = i
            self.total_steps = 5
            
            # Emit step
            step = StepLog(
                step_number=i,
                action_type=step_types[i-1],
                params={"x": 100*i, "y": 200*i} if step_types[i-1] == "CLICK" else {"text": "hello"},
                status="success"
            )
            self._on_step(step)
            
            # Update progress
            self.query_one("#progress", Static).update(f"Step {i} / 5")
            
            await asyncio.sleep(0.5)  # Simulate work
        
        if not self.agent.is_stopped():
            self.status = "complete"
            log.write_line("[✓ Task Complete]")
        else:
            self.status = "failed"
            log.write_line("[✗ Task Failed]")
        
        self._update_key_display()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "btn-send":
            input_widget = self.query_one("#task-input", Input)
            task = input_widget.value.strip()
            if task:
                self.task_name = task
                self.run_task_async(task)
                input_widget.value = ""
        
        elif button_id == "btn-abort":
            self.agent.abort()
            self.status = "failed"
            log = self.query_one("#log-view", Log)
            log.write_line("[⚠ ABORTED - Failsafe triggered]")
            self.exit()
        
        elif button_id == "btn-pause":
            if self.paused:
                self.agent.resume()
                self.paused = False
                self.query_one("#btn-pause", Button).label = "PAUSE"
            else:
                self.agent.pause()
                self.paused = True
                self.query_one("#btn-pause", Button).label = "RESUME"
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        task = event.value.strip()
        if task:
            self.task_name = task
            self.run_task_async(task)
            event.input.value = ""


def main():
    """Entry point."""
    app = JarvisApp()
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test TUI imports**

Run: `python -c "from jarvis.ui.textual_app import JarvisApp; print('OK')"`
Expected: OK

- [ ] **Step 3: Run TUI briefly to verify layout**

Run: `timeout 3 python -m jarvis.ui.textual_app` (or Ctrl+C)
Expected: Window appears with 3 panels

- [ ] **Step 4: Commit**

---

## Task 3: Integrate with Core Task Execution

**Files:**
- Modify: `jarvis/lib/__init__.py` (Task 1)
- Modify: `jarvis/ui/textual_app.py` (Task 2)

- [ ] **Step 1: Update AgentLib to use actual TaskManager**

Modify `jarvis/lib/__init__.py` to integrate real task execution:

```python
# Add to AgentLib.run_task() after creating TaskState
@work(exclusive=True)
async def _execute_task_loop(self, task_name: str):
    """Execute task loop in background."""
    try:
        result = self.task_manager.execute_task(task_name)
        
        # Process action history into step logs
        for i, action in enumerate(self.task_manager.get_history(), 1):
            step = StepLog(
                step_number=i,
                action_type=action.get("action", "unknown"),
                params=action.get("params", {}),
                status="success" if action.get("success", True) else "failed"
            )
            self._step_logs.append(step)
            if self.on_step:
                self.on_step(step)
            
            # Check pause
            while self._paused:
                await asyncio.sleep(0.1)
            
            if self._stopped:
                break
        
        if self._task_state:
            self._task_state.status = "complete" if result.success else "failed"
            self._task_state.total_steps = result.total_actions
    
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        if self._task_state:
            self._task_state.status = "failed"
            self._task_state.error = str(e)
```

- [ ] **Step 2: Update TUI to use real execution**

Modify `textual_app.py` `run_task_async` to call real execution.

- [ ] **Step 3: Test full execution flow**

Run TUI, type "open browser", verify real actions execute.

- [ ] **Step 4: Commit**

---

## Task 4: Add Confirmation Modal

**Files:**
- Modify: `jarvis/ui/textual_app.py`

- [ ] **Step 1: Add confirm dialog for CONFIRM tier**

Add modal that halts execution and waits for user input:

```python
class ConfirmDialog(Modal):
    """Confirmation dialog for high-safety actions."""
    
    def compose(self) -> ComposeResult:
        yield Static("Confirm this action?", id="confirm-msg")
        with Horizontal():
            yield Button("YES", id="btn-yes", variant="primary")
            yield Button("NO", id="btn-no", variant="error")
```

- [ ] **Step 2: Integrate with execution flow**

Check safety_tier before each action, show modal if CONFIRM.

- [ ] **Step 3: Test confirmation workflow**

Run TUI, trigger CONFIRM-tier action, verify modal appears.

- [ ] **Step 4: Commit**

---

## Task 5: Failsafe Integration

**Files:**
- Modify: `jarvis/ui/textual_app.py`

- [ ] **Step 1: Bind ESC key to failsafe**

```python
def on_key(self, event: Key) -> None:
    if event.key == "escape":
        self.agent.abort()
        self.exit()
```

- [ ] **Step 2: Verify failsafe works**

Run TUI, press ESC, verify mouse moves to (0,0) and app exits.

- [ ] **Step 3: Final commit**

---

## Summary

| Task | Files | Status |
|------|-------|--------|
| 1: Library module | jarvis/lib/__init__.py | Pending |
| 2: TUI App | jarvis/ui/textual_app.py | Pending |
| 3: Core integration | (above modified) | Pending |
| 4: Confirmation modal | textual_app.py | Pending |
| 5: Failsafe | textual_app.py | Pending |