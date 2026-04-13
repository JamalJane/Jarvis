"""JARVIS Basic TUI - works on any terminal"""

import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

# Basic ANSI codes that work everywhere
CLEAR = "\033[2J\033[H"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[36m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
BG_DARK = "\033[40m"
WHITE = "\033[37m"


class BasicTUI:
    def __init__(self):
        self.running = False
        self.task = ""
        self.steps = []
        self.key_idx = 1
    
    def init(self):
        from jarvis.lib import AgentLib, StepLog
        
        def on_step(step):
            self.steps.append(step)
        
        self.agent = AgentLib(on_step=on_step)
    
    def render(self):
        print(CLEAR, end="")
        
        # Header
        task_display = f" -> {self.task[:20]}" if self.task else ""
        print(f"{GREEN}{BOLD}JARVIS v1.0{RESET} [*] Key {self.key_idx}/4{task_display}")
        print("-" * 50)
        
        # Left panel - Agent Log
        left_lines = ["AGENT LOG", ""]
        for step in self.steps[-8:]:
            icon = "OK" if step.status == "success" else ("..." if step.status == "running" else "X")
            color = GREEN if step.status == "success" else (YELLOW if step.status == "running" else RED)
            
            params = step.params
            p = ""
            if "x" in params and "y" in params:
                p = f"({params['x']},{params['y']})"
            elif "text" in params:
                p = f'"{params["text"][:10]}"'
            
            left_lines.append(f"Step {step.step_number}: {step.action_type} {p} {color}{icon}{RESET}")
        
        if not left_lines[1:]:
            left_lines.append(f"{DIM}(no steps yet){RESET}")
        
        # Right panel - Status
        right_lines = ["STATUS", ""]
        task_state = self.agent.get_task_state() if self.agent else None
        current = task_state.status if task_state else "Idle"
        
        right_lines.append(f"Action:  {current}")
        right_lines.append(f"Screen: -")
        right_lines.append(f"Step:   {len(self.steps)}")
        right_lines.append(f"Keys:   K1:OK  K2:ACTIVE  K3:OK  K4:OK")
        right_lines.append(f"Safety: AUTO")
        
        # Print side by side
        max_lines = max(len(left_lines), len(right_lines))
        for i in range(max_lines):
            left = left_lines[i] if i < len(left_lines) else ""
            right = right_lines[i] if i < len(right_lines) else ""
            print(f"{left:25} | {right}")
        
        print("-" * 50)
        print(f"{DIM}> SEND  ABORT  PAUSE{RESET}")
        print("> ", end="", flush=True)
    
    def start(self):
        self.init()
        self.running = True
        
        try:
            while True:
                self.render()
                self.handle_input()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting JARVIS...")
            import os
            os._exit(0)
    
    def handle_input(self):
        try:
            line = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting JARVIS...")
            import os
            os._exit(0)
        except Exception:
            return
        
        if not line:
            return
            
        if line.lower() in ["/help", "help", "?"]:
            print(CLEAR, end="")
            print("\n" + "="*50)
            print(" JARVIS TUI COMMANDS")
            print("="*50)
            print("  /help, help, ? : Show this help menu")
            print("  exit, quit, q  : Shutdown JARVIS completely")
            print("  abort          : Emergency stop current task (moves mouse to 0,0)")
            print("  pause          : Do nothing, just re-renders")
            print("  [any text]     : Send text/task to JARVIS AI (e.g. 'open notepad')")
            print("="*50)
            input("\nPress Enter to return...")
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
            return
        
        self.task = line
        self.steps = []
        
        def run_it():
            try:
                self.agent.run_task(line)
            except Exception as e:
                pass
            print(f"\n{GREEN}{BOLD}--- TASK COMPLETE. PRESS ENTER TO REFRESH ---{RESET}")
            print("> ", end="", flush=True)

        threading.Thread(target=run_it, daemon=True).start()
        time.sleep(0.3)


def main():
    tui = BasicTUI()
    tui.start()


if __name__ == "__main__":
    main()