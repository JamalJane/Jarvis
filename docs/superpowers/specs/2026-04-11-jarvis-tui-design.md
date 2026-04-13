# JARVIS TUI Specification

**Date:** 2026-04-11  
**Project:** JARVIS Terminal UI  
**Type:** Feature Design

---

## 1. Overview

Build a Textual-based terminal UI for JARVIS that wraps the existing automation engine. Replaces the current prompt_toolkit REPL with a 3-panel layout showing real-time task progress, agent logs, and status.

**Goals:**
- Real-time UI updates as tasks execute
- Visual feedback on each action step (color-coded logs)
- Gemini key status at a glance
- Failsafe abort via ESC or ABORT button

---

## 2. Architecture

### 2.1 Integration Model

Refactor existing core into a reusable library, then TUI orchestrates it:

```
┌─────────────────────────────────────────┐
│              TUI (textual)              │
│  ┌─────────────────────────────────┐  │
│  │     JarvisApp (Screen)            │  │
│  │  - HeaderBar                   │  │
│  │  - AgentLogPanel              │  │
│  │  - StatusPanel               │  │
│  │  - InputBar                 │  │
│  └─────────────────────────────────┘  │
│                    │                    │
│              ┌────┴────┐              │
│              │ AgentLib │   ← NEW     │
│              └────┬────┘              │
│                   │                   │
│    ┌──────────────┼──────────────┐    │
│    ▼              ▼              ▼    │
│ APIManager  TaskManager  Automation │
└─────────────────────────────────┘
```

### 2.2 Library Module: `jarvis/lib/__init__.py`

New module exposing:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

class SafetyTier(Enum):
    AUTO = "auto"      # Execute without prompt
    LOG = "log"        # Log only, require approval
    CONFIRM = "confirm" # Explicit user confirmation

@dataclass
class StepLog:
    step_number: int
    action_type: str
    params: dict
    status: str  # "success" | "running" | "failed" | "info"
    result: str = ""

@dataclass
class TaskState:
    task_name: str
    status: str  # "idle" | "running" | "paused" | "complete" | "failed"
    current_step: int
    total_steps: int
    last_screenshot_path: str
    safety_tier: SafetyTier
    error: Optional[str] = None

class AgentLib:
    def __init__(self, on_step: Callable[[StepLog], None]):
        self.on_step = on_step
        self._task_state: Optional[TaskState] = None
        self._paused = False
        self._stopped = False

    def run_task(self, task_name: str) -> TaskState:
        """Run task in background thread. Updates via callback."""

    def pause(self):
        """Pause after current step completes."""

    def abort(self):
        """Stop immediately, move mouse to 0,0."""

    def get_api_status(self) -> dict:
        """Return key status for header display."""

    def get_key_status_full(self) -> dict:
        """Detailed key status for status panel."""
```

---

## 3. UI Components

### 3.1 Layout

```
┌────���────────────────────────────────────────┐
│  JARVIS  v1.0  [● ONLINE]  Gemini Key: 2/4  │
├──────────────────┬──────────────────────────┤
│                  │                          │
│   AGENT LOG      │    STATUS PANEL         │
│                  │                          │
│  Step 1: ✓       │    Action: click (100,200)│
│  Step 2: ✓       │    Screenshot: /p/x.png │
│  Step 3: ⟳       │    Step 4 / 25          │
│                  │    Key 1: OK           │
│                  │    Key 2: ACTIVE        │
│                  │    Key 3: OK           │
│                  │    Key 4: OK           │
│                  │    Safety: AUTO          │
├──────────────────┴──────────────────────────┤
│  > task...         [SEND]  [ABORT]  [PAUSE]  │
└─────────────────────────────────────────────┘
```

### 3.2 Header Bar

- **JARVIS v1.0**: Fixed text
- **Status dot**: Circle icon
  - Green fill = running (status == "running")
  - Red fill = stopped/failed (status == "failed")
  - Yellow fill = waiting for confirm (status == "paused" + confirm needed)
- **Active key**: "Gemini Key: 2/4" format from `api_manager.current_key_index` + 1
- **Task name**: Truncated to 30 chars, ellipsis if longer

### 3.3 Agent Log Panel (Left)

Scrollable list with color-coded entries:

| Status | Color | Icon |
|--------|-------|------|
| success | green (#00ff88) | ✓ |
| running | yellow (#ffcc00) | ⟳ |
| failed | red (#ff4444) | ✗ |
| info | blue (#4499ff) | 📷 |

Each entry format:
```
Step 5: CLICK (150, 340) → Success
Step 6: TYPE "hello world" → Success
Step 7: SCREENSHOT → Taken
```

Auto-scrolls to bottom on new entries.

### 3.4 Status Panel (Right)

| Field | Source |
|-------|--------|
| Current action | Last StepLog.action_type + params |
| Screenshot path | task_state.last_screenshot_path |
| Steps remaining | f"Step {current} / {total}" |
| Key status | Table: Key 1: [OK|ACTIVE|FAIL]... |
| Safety tier | task_state.safety_tier.name |

### 3.5 Input Bar (Bottom)

- Text input: placeholder "Enter task..."
- [SEND] button: Submit task
- [ABORT] button: Trigger failsafe + stop
- [PAUSE] button: Toggle pause state

---

## 4. Behavior

### 4.1 Task Execution Flow

```
User inputs task → SEND button / Enter
        ↓
AgentLib.run_task(task) starts in worker thread
        ↓
For each step:
  - Execute action via TaskManager
  - Emit StepLog via callback
  - TUI updates log panel + status panel
        ↓
  Check safety_tier:
    - AUTO: Continue
    - LOG: Log only
    - CONFIRM: Show modal → User clicks Yes/No
        ↓
Task completes → Show banner: "✓ Task Complete" (green) or "✗ Failed" (red)
```

### 4.2 Failsafe (ABORT / ESC)

```python
def failsafe_trigger():
    pyautogui.moveTo(0, 0)  # Move to corner
    raise SystemExit("Failsafe triggered")
```

### 4.3 Error States

- **AllKeysExhaustedError**: Red banner "⚠ All Gemini keys exhausted"
- **Task failed**: Red banner with error message
- **Task complete**: Green banner "✓ Task completed (N actions)"

---

## 5. Style

### 5.1 Colors

| Element | Value |
|---------|-------|
| Background | #0d1117 |
| Panel bg | #161b22 |
| Text primary | #e6edf3 |
| Text secondary | #8b949e |
| Success green | #00ff88 |
| Warning yellow | #ffcc00 |
| Error red | #ff4444 |
| Info blue | #4499ff |
| Border | #30363d |

### 5.2 Typography

- Font: Monospace throughout (Textual default)
- Header: Bold
- Log entries: Default
- Status panel: Default

### 5.3 Spacing

- Panel padding: 1 unit
- Panel borders: Minimal, #30363d
- No excessive decoration

---

## 6. Acceptance Criteria

1. ✓ App starts showing idle state with empty log
2. ✓ User types task, hits Enter → task runs
3. ✓ Log panel shows each step with correct color/icon
4. ✓ Status panel updates with current action + key status
5. ✓ PAUSE button pauses after current step
6. ✓ ABORT / ESC moves mouse to 0,0 and exits
7. ✓ CONFIRM tier shows modal before proceeding
8. ✓ AllKeysExhaustedError shows red banner
9. ✓ Task complete shows success banner

---

## 7. Files

```
jarvis/
  lib/                  ← NEW
    __init__.py         # AgentLib, StepLog, TaskState, SafetyTier
  ui/
    textual_app.py     ← NEW (main TUI app)
```

Existing files unchanged. TUI imports from `jarvis.lib`.