"""
JARVIS Console TUI
Simple blocking terminal UI that works on any terminal
"""

import os
import sys

# Fix Unicode on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import threading
import time
from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from jarvis.lib import AgentLib, StepLog, TaskState, SafetyTier


console = Console(force_terminal=True)


def main():
    print("\033[?1049l\033[?1000l\033[?25l", end="")  # Enter alternate screen, enable mouse, hide cursor
    
    state = {"running": False, "paused": False, "task": "", "steps": [], "key_idx": 1}
    
    def on_step(step: StepLog):
        state["steps"].append(step)
    
    agent = AgentLib(on_step=on_step)
    
    try:
        while True:
            _render(state)
            _handle_input(state)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        print("\033[?1049h\033[?1000h\033[?25h", end="")  # Exit alternate screen


def _render(state):
    console.clear()
    
    width = 60
    
    header = Text(f"JARVIS v1.0  [*] Key {state['key_idx']}/4", style="bold green")
    if state["task"]:
        header.append(f"  → {state['task'][:25]}")
    
    console.print(Panel(header, style="on rgb(22,27,34)", width=width))
    
    log_table = Table(box=None, show_header=True, title="AGENT LOG", padding=(0, 1))
    log_table.add_column("step", style="dim", width=5)
    log_table.add_column("action", style="white", width=15)
    log_table.add_column("status", width=8)
    
    for step in state["steps"][-8:]:
        icon = "OK" if step.status == "success" else ("..." if step.status == "running" else ("X" if step.status == "failed" else ("#")))
        color = "green" if step.status == "success" else ("yellow" if step.status == "running" else ("red" if step.status == "failed" else "cyan"))
        
        params = step.params
        params_str = ""
        if "x" in params and "y" in params:
            params_str = f"({params['x']},{params['y']})"
        elif "text" in params:
            params_str = f'"{params["text"][:12]}..."'
        
        log_table.add_row(f"{step.step_number}", f"{step.action_type} {params_str}", f"[{color}]{icon}[/]")
    
    status_table = Table(box=None, show_header=True, title="STATUS PANEL", padding=(0, 1))
    status_table.add_column("field", style="dim", width=15)
    status_table.add_column("value", style="white")
    
    task_state = agent.get_task_state() if agent else None
    current = task_state.action_type if task_state else "Idle"
    progress = f"Step {len(state['steps'])}"
    
    status_table.add_row("Current Action:", current)
    status_table.add_row("Screenshot:", task_state.last_screenshot_path if task_state else "None")
    status_table.add_row("Progress:", progress)
    status_table.add_row("Key 1:", "OK")
    status_table.add_row("Key 2:", "ACTIVE" if state["key_idx"] == 2 else "OK")
    status_table.add_row("Safety:", "AUTO")
    
    main_table = Table.grid(padding=0)
    main_table.add_column("log", width=30, ratio=1)
    main_table.add_column("status", width=30, ratio=1)
    main_table.add_row(
        Panel(log_table, style="on rgb(22,27,34)"),
        Panel(status_table, style="on rgb(22,27,34)")
    )
    
    console.print(main_table)
    
    console.print(Panel("> SEND  ABORT  PAUSE", style="on rgb(22,27,34)", width=width))


def _handle_input(state):
    print("\n> ", end="", flush=True)
    try:
        line = input().strip()
    except:
        return
    
    if not line:
        return
    
    if line.lower() in ["exit", "quit", "q"]:
        raise KeyboardInterrupt()
    
    if line.lower() == "abort":
        try:
            import pyautogui
            pyautogui.moveTo(0, 0)
        except:
            pass
        print("Aborted!")
        raise KeyboardInterrupt()
    
    if line.lower() == "pause":
        state["paused"] = not state["paused"]
        return
    
    state["task"] = line
    state["running"] = True
    state["steps"] = []
    
    def run_it():
        try:
            result = agent.run_task(line)
        except Exception as e:
            state["steps"].append(StepLog(0, "error", {}, "failed", str(e)))
        state["running"] = False
    
    threading.Thread(target=run_it, daemon=True).start()
    time.sleep(0.5)


if __name__ == "__main__":
    main()