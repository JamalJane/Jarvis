"""
JARVIS Rich-based TUI
A simple terminal UI using Rich library (works on any terminal)
"""

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.style import Style
from rich.color import Color

from jarvis.lib import AgentLib, StepLog, TaskState, SafetyTier


console = Console()

BG = Color.from_rgb(13, 17, 23)
PANEL_BG = Color.from_rgb(22, 27, 34)
TEXT_PRIMARY = Color.from_rgb(230, 237, 243)
TEXT_SECONDARY = Color.from_rgb(139, 148, 158)
GREEN = Color.from_rgb(0, 255, 136)
YELLOW = Color.from_rgb(255, 204, 0)
RED = Color.from_rgb(255, 68, 68)
BLUE = Color.from_rgb(68, 153, 255)


class RichTUI:
    def __init__(self):
        self.console = Console()
        self.agent: Optional[AgentLib] = None
        self._paused = False
        self._running = False
        self._task_name = ""
        self._step_logs: list[StepLog] = []
        self._step_count = 0
        self._key_status = {}
        
    def init(self):
        def on_step(step: StepLog):
            self._step_count += 1
            self._step_logs.append(step)
        
        self.agent = AgentLib(on_step=on_step)
        self._update_key_status()
        
    def _update_key_status(self):
        if self.agent:
            status = self.agent.get_key_status_full()
            self._key_status = status.get("status", {})
    
    def build_layout(self) -> Layout:
        layout = Layout()
        
        header = Panel(
            Text("JARVIS v1.0  ● ONLINE  " + f"Gemini Key: {self._get_active_key()}/4"),
            style=PANEL_BG,
            subtitle=self._task_name[:30] if self._task_name else "Idle"
        )
        return layout
    
    def _get_active_key(self) -> int:
        try:
            status = self.agent.get_api_status() if self.agent else {}
            return status.get("current", 1)
        except (AttributeError, KeyError, Exception):
            return 1
    
    def render(self):
        log_content = self._render_log()
        status_content = self._render_status()
        
        left_panel = Panel(
            log_content,
            title="AGENT LOG",
            style=PANEL_BG,
            border_style=TEXT_SECONDARY
        )
        
        right_panel = Panel(
            status_content,
            title="STATUS PANEL",
            style=PANEL_BG,
            border_style=TEXT_SECONDARY
        )
        
        table = Table.grid(padding=0)
        table.add_column("log", width=40, ratio=2)
        table.add_column("status", width=60, ratio=3)
        table.add_row(left_panel, right_panel)
        
        return table
    
    def _render_log(self) -> Text:
        if not self._step_logs:
            return Text("No steps yet...", style=TEXT_SECONDARY)
        
        lines = []
        for step in self._step_logs[-10:]:
            icon_map = {"success": "✓", "running": "⟳", "failed": "✗", "info": "📷"}
            color_map = {"success": GREEN, "running": YELLOW, "failed": RED, "info": BLUE}
            
            icon = icon_map.get(step.status, "?")
            color = color_map.get(step.status, TEXT_PRIMARY)
            
            params = step.params
            params_str = ""
            if "x" in params and "y" in params:
                params_str = f"({params['x']}, {params['y']})"
            elif "text" in params:
                params_str = f'"{params["text"]}"'
            
            line = f"Step {step.step_number}: {step.action_type} {params_str}"
            lines.append(Text(line, style=color))
        
        return Text("\n").join(lines)
    
    def _render_status(self) -> Table:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("label", style=TEXT_SECONDARY, width=15)
        table.add_column("value", style=TEXT_PRIMARY)
        
        task_state = self.agent.get_task_state() if self.agent else None
        current_action = task_state.action_type if task_state else "Idle"
        
        table.add_row("Current Action:", current_action)
        table.add_row("Screenshot:", task_state.last_screenshot_path if task_state else "None")
        table.add_row("Progress:", f"Step {self._step_count}")
        table.add_row("API Keys:", self._render_keys())
        table.add_row("Safety:", "AUTO")
        
        return table
    
    def _render_keys(self) -> Text:
        lines = []
        active_key = self._get_active_key()
        
        for i in range(1, 5):
            key_name = f"Key {i}"
            if i == active_key:
                lines.append(f"{key_name}: ACTIVE")
            elif f"Gemini {i}" in self._key_status:
                info = self._key_status.get(f"Gemini {i}", {})
                if info.get("failed"):
                    lines.append(f"{key_name}: FAIL")
                else:
                    remaining = info.get("remaining", 0)
                    lines.append(f"{key_name}: OK({remaining})")
            else:
                lines.append(f"{key_name}: OK")
        
        return Text("  ".join(lines), style=TEXT_PRIMARY)
    
    def run_loop(self):
        with Live(self.render(), console=console, refresh_per_second=4) as live:
            while True:
                time.sleep(0.25)
                live.update(self.render())


def main():
    tui = RichTUI()
    tui.init()
    tui.run_loop()


if __name__ == "__main__":
    main()