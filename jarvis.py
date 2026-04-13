#!/usr/bin/env python3
"""JARVIS - Autonomous AI Assistant & Screen Automation Agent"""

import logging
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/jarvis.log"),
        logging.StreamHandler()
    ]
)

def run_tui(args):
    from jarvis.ui.basic_tui import main as tui_main
    tui_main()

def run_cli(args):
    from jarvis.main_loop import main as cli_main
    try:
        cli_main()
    except KeyboardInterrupt:
        print("\nShutting down...")

def run_screen(args):
    # Route for jarvis_control logic
    import time
    from datetime import datetime
    
    task = args.task
    if isinstance(task, list):
        task = " ".join(task)
        
    if not task:
        print("📋 Enter task description: ", end="", flush=True)
        task = input().strip()

    if not task:
        print("❌ No task provided. Exiting.")
        sys.exit(1)

    print(f"\n🚀 JARVIS Screen Control")
    print(f"   Task: {task}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   ⚠️  FAILSAFE: Move mouse to TOP-LEFT corner to abort immediately.\n")
    print("─" * 60)

    try:
        from jarvis.screen_control.screen_controller import ScreenController
        from jarvis.screen_control.gemini_client import AllKeysExhaustedError
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed: pip install -r requirements.txt")
        sys.exit(1)

    controller = ScreenController()
    start_time = time.time()

    try:
        history = controller.run_task(task)
    except AllKeysExhaustedError:
        print("\n⚠️  All Gemini keys exhausted. Please try again later.")
        sys.exit(1)
    except SystemExit as e:
        print(f"\n{e}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user.")
        sys.exit(0)

    duration = time.time() - start_time
    print("\n" + "─" * 60)
    print(f"📊 TASK SUMMARY")
    print(f"   Steps taken : {len(history)}")
    print(f"   Duration    : {duration:.1f}s")

    if history:
        last = history[-1]
        last_action = last["action"].get("action", "?")
        if last_action == "done":
            print(f"   Status      : ✅ SUCCESS")
            print(f"   Message     : {last['action'].get('message', 'Completed.')}")
        elif last_action == "failed":
            print(f"   Status      : ❌ FAILED")
            print(f"   Reason      : {last['action'].get('reason', 'Unknown failure.')}")
        else:
            print(f"   Status      : ⚠️  Max steps reached without terminal action.")

    print("─" * 60)
    print(f"   Logs saved to: logs/")

def run_daemon(args):
    from jarvis.daemon import start_daemon
    start_daemon()

def run_web(args):
    import uvicorn
    from jarvis.web.server import app
    print("Starting Web Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

def main():
    parser = argparse.ArgumentParser(
        description="JARVIS - Autonomous AI Assistant",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # TUI Command (Default)
    parser_tui = subparsers.add_parser("tui", help="Start the Text User Interface")
    parser_tui.set_defaults(func=run_tui)
    
    # CLI Command
    parser_cli = subparsers.add_parser("cli", help="Start the basic interactive terminal loop")
    parser_cli.set_defaults(func=run_cli)
    
    # Screen Command
    parser_screen = subparsers.add_parser("screen", help="Run a screen automation task")
    parser_screen.add_argument("task", nargs="*", default=[], help="The task description. If empty, asks interactively.")
    parser_screen.set_defaults(func=run_screen)
    
    # Daemon Command
    parser_daemon = subparsers.add_parser("daemon", help="Start the background daemon")
    parser_daemon.set_defaults(func=run_daemon)

    # Web Command
    parser_web = subparsers.add_parser("web", help="Start the web server")
    parser_web.set_defaults(func=run_web)

    args = parser.parse_args()

    # Default to TUI if no command is provided
    if args.command is None:
        run_tui(args)
    else:
        args.func(args)

if __name__ == "__main__":
    main()