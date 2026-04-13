"""
JARVIS Textual TUI Application
A 3-panel terminal UI using Textual framework
"""

import threading
from dataclasses import dataclass
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Static, Log, Input


@dataclass
class LogEntry:
    message: str
    status: str


class JarvisApp(App):
    CSS = """
    Screen {
        background: rgb(13,17,23);
    }
    #header_bar {
        background: rgb(22,27,34);
        color: rgb(230,237,243);
        height: 1;
        dock: top;
    }
    #main_container {
        height: auto;
        layout: horizontal;
    }
    #left_panel {
        width: 40%;
        background: rgb(22,27,34);
        border-right: solid rgb(48,54,61);
    }
    #left_header {
        color: rgb(139,148,158);
        padding: 0 1;
    }
    #log_widget {
        background: rgb(22,27,34);
        color: rgb(230,237,243);
        height: 100%;
    }
    #right_panel {
        width: 60%;
        background: rgb(22,27,34);
    }
    #right_header {
        color: rgb(139,148,158);
        padding: 0 1;
    }
    #status_container {
        background: rgb(22,27,34);
        padding: 1 2;
    }
    .status_label {
        color: rgb(139,148,158);
    }
    #input_bar {
        background: rgb(22,27,34);
        height: 3;
        dock: bottom;
        padding: 1 2;
    }
    #input_field {
        width: 70%;
        background: rgb(13,17,23);
        color: rgb(230,237,243);
        border: solid rgb(48,54,61);
    }
    """

    BINDINGS = [
        ("escape", "abort", "Abort"),
    ]

    def __init__(self):
        super().__init__()
        self.agent_lib: Optional[object] = None
        self._paused = False
        self._running = False
        self._current_task = ""
        self._log_entries: list[LogEntry] = []
        self._step_count = 0

    def compose(self) -> ComposeResult:
        yield Static("JARVIS v1.0  [● ONLINE]  Gemini Key: 2/4", id="header_bar")
        with Container(id="main_container"):
            with Vertical(id="left_panel"):
                yield Static("AGENT LOG", id="left_header")
                yield Log(id="log_widget")
            with Vertical(id="right_panel"):
                yield Static("STATUS PANEL", id="right_header")
                with Container(id="status_container"):
                    yield Static("Current Action: Idle", classes="status_label")
                    yield Static("Screenshot: None", classes="status_label")
                    yield Static("Progress: Step 0 / 0", classes="status_label")
                    yield Static("Key 1: OK  Key 2: ACTIVE  Key 3: OK  Key 4: OK", classes="status_label")
                    yield Static("Safety: AUTO", classes="status_label")
        with Horizontal(id="input_bar"):
            yield Input(placeholder="Enter task...", id="input_field")
            yield Button("SEND", variant="primary", id="btn_send")
            yield Button("ABORT", variant="error", id="btn_abort")
            yield Button("PAUSE", variant="warning", id="btn_pause")

    def on_mount(self) -> None:
        try:
            from jarvis.lib import AgentLib
            
            def on_step(step):
                self._step_count += 1
                icon_map = {"success": "✓", "running": "⟳", "failed": "✗", "info": "📷"}
                color_map = {
                    "success": "rgb(0,255,136)",
                    "running": "rgb(255,204,0)",
                    "failed": "rgb(255,68,68)",
                    "info": "rgb(68,153,255)"
                }
                icon = icon_map.get(step.status, "?")
                color = color_map.get(step.status, "rgb(230,237,243)")
                params = step.params
                params_str = ""
                if "x" in params and "y" in params:
                    params_str = f"({params['x']}, {params['y']})"
                elif "text" in params:
                    params_str = f'"{params["text"]}"'
                elif "key" in params:
                    params_str = params["key"]
                
                msg = f"[{color}]{icon}[/] Step {step.step_number}: {step.action_type} {params_str}"
                self.add_log_raw(msg)
                
                self.call_from_thread(self._update_progress, step.step_number)
            
            self.agent_lib = AgentLib(on_step=on_step)
            self._update_key_status()
        except Exception as e:
            self.log_error(f"Init error: {e}")

    def _update_key_status(self):
        if self.agent_lib:
            try:
                status = self.agent_lib.get_key_status_full()
                lines = []
                for i, (name, info) in enumerate(status.get("status", {}).items(), 1):
                    if info.get("failed"):
                        status_text = "FAIL"
                    else:
                        remaining = info.get("remaining", 0)
                        status_text = f"OK({remaining})"
                    lines.append(f"Key {i}: {status_text}")
                
                self.query_one("#status_container > Static:nth-child(4)").update("  ".join(lines))
            except Exception:
                pass

    def _update_progress(self, step: int):
        try:
            self.query_one("#status_container > Static:nth-child(3)").update(f"Progress: Step {step}")
        except Exception:
            pass

    def log_error(self, msg: str):
        self.add_log(f"[rgb(255,68,68)]✗[/] {msg}")

    def log_success(self, msg: str):
        self.add_log(f"[rgb(0,255,136)]✓[/] {msg}")

    def log_info(self, msg: str):
        self.add_log(f"[rgb(68,153,255)]📷[/] {msg}")

    def action_send(self) -> None:
        input_widget = self.query_one("#input_field", Input)
        task = input_widget.value.strip()
        if task:
            self._current_task = task
            self._running = True
            self._step_count = 0
            input_widget.value = ""
            
            header = self.query_one("#header_bar", Static)
            task_display = task[:25] + "..." if len(task) > 25 else task
            header.update(f"JARVIS v1.0  [● ONLINE]  {task_display}")
            
            self.add_log(f"[rgb(230,237,243)]Starting: {task}[/]")
            threading.Thread(target=self._run_task, args=(task,), daemon=True).start()

    def action_abort(self) -> None:
        try:
            import pyautogui
            pyautogui.moveTo(0, 0)
        except Exception:
            pass
        self._running = False
        if self.agent_lib:
            try:
                self.agent_lib.abort()
            except Exception:
                pass
        self.log_error("ABORTED - Failsafe triggered")
        self.exit()

    def action_pause(self) -> None:
        self._paused = not self._paused
        if self.agent_lib:
            try:
                if self._paused:
                    self.agent_lib.pause()
                else:
                    self.agent_lib.resume()
            except Exception:
                pass
        status = "PAUSED" if self._paused else "RESUMED"
        status_color = "rgb(255,204,0)" if self._paused else "rgb(0,255,136)"
        self.add_log(f"[{status_color}]{status}[/]")
        
        btn = self.query_one("#btn_pause", Button)
        btn.label = "RESUME" if self._paused else "PAUSE"

    def _run_task(self, task: str) -> None:
        if self.agent_lib:
            try:
                result = self.agent_lib.run_task(task)
                status = result.status if result else "failed"
            except Exception as e:
                self.log_error(f"Error: {e}")
                status = "failed"
        else:
            status = "failed"
        
        self._running = False
        self.call_from_thread(self._task_complete, status)

    def _task_complete(self, status: str):
        header = self.query_one("#header_bar", Static)
        if status == "complete":
            header.update("JARVIS v1.0  [● ONLINE]  ✓ Complete")
            self.log_success(f"Task complete ({self._step_count} steps)")
        else:
            header.update("JARVIS v1.0  [● ONLINE]  ✗ Failed")
            self.log_error(f"Task failed")
        
        self._update_key_status()

    def add_log(self, message: str) -> None:
        self._log_entries.append(LogEntry(message=message, status=""))
        self.call_from_thread(self._update_log_display)

    def add_log_raw(self, message: str) -> None:
        self._log_entries.append(LogEntry(message=message, status=""))
        self.call_from_thread(self._update_log_display)

    def _update_log_display(self) -> None:
        log_widget = self.query_one("#log_widget", Log)
        if self._log_entries:
            entry = self._log_entries[-1]
            log_widget.write(entry.message, shrink=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_send":
            self.action_send()
        elif button_id == "btn_abort":
            self.action_abort()
        elif button_id == "btn_pause":
            self.action_pause()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.value.strip():
            self.action_send()


def main():
    app = JarvisApp()
    app.run()


if __name__ == "__main__":
    main()