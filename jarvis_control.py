"""
jarvis_control.py — Entry point for the JARVIS screen control automation module.

Usage:
    python jarvis_control.py "open chrome and go to gmail.com"
    python jarvis_control.py          # reads task from stdin

Prints step-by-step progress to terminal.
On completion: prints summary (steps taken, success/fail, duration).
"""

import sys
import time
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    # Determine task from argument or stdin
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
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

    # Import here so startup errors are clean
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
        print("\n⚠️  All Gemini keys exhausted. Please try again later or add more keys to .env.")
        sys.exit(1)
    except SystemExit as e:
        # Failsafe triggered
        print(f"\n{e}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user.")
        sys.exit(0)

    duration = time.time() - start_time

    # Summary
    print("\n" + "─" * 60)
    print(f"📊 TASK SUMMARY")
    print(f"   Steps taken : {len(history)}")
    print(f"   Duration    : {duration:.1f}s")

    if history:
        last = history[-1]
        last_action = last["action"].get("action", "?")
        if last_action == "done":
            msg = last["action"].get("message", "Completed.")
            print(f"   Status      : ✅ SUCCESS")
            print(f"   Message     : {msg}")
        elif last_action == "failed":
            reason = last["action"].get("reason", "Unknown failure.")
            print(f"   Status      : ❌ FAILED")
            print(f"   Reason      : {reason}")
        else:
            print(f"   Status      : ⚠️  Max steps reached without terminal action.")

    print("─" * 60)
    print(f"   Logs saved to: logs/")


if __name__ == "__main__":
    main()
