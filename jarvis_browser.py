"""
jarvis_browser.py — Entry point for JARVIS browser automation.

Controls the user's REAL Chrome browser (logged-in profile, real cookies)
via Playwright CDP-attach.  Mirrors the structure of jarvis_control.py.

Usage:
    python jarvis_browser.py "go to gmail and find emails from amazon"
    python jarvis_browser.py "search youtube for lo-fi beats and play first result"
    python jarvis_browser.py        # reads task from stdin
"""

import sys
import time
from datetime import datetime

# Force UTF-8 output so emoji and special chars render correctly on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


# ── ANSI colour helpers (degrade gracefully on plain terminals) ───────────────

def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m"


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m"


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m"


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Resolve task from CLI arg or stdin
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        print("📋 Enter task description: ", end="", flush=True)
        task = input().strip()

    if not task:
        print("❌ No task provided. Exiting.")
        sys.exit(1)

    # 2. Pretty header
    print()
    print(_bold("🌐 JARVIS Browser Control"))
    print(f"   Task : {task}")
    print(f"   Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   ℹ️   Chrome must be closed (or already running with --remote-debugging-port=9222)")
    print("─" * 65)

    # 3. Lazy imports (clean startup error messages)
    try:
        from jarvis.browser_control.browser_controller import BrowserController
        from jarvis.browser_control.chrome_launcher import ChromeLaunchError
        from jarvis.screen_control.gemini_client import AllKeysExhaustedError
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed:")
        print("     pip install -r requirements.txt")
        print("     playwright install chromium")
        sys.exit(1)

    # 4. Create controller
    controller = BrowserController()
    start_time = time.time()
    result: dict = {}

    try:
        # 5. Attach to Chrome (launches if not running)
        print("🔗 Attaching to Chrome…")
        controller.start()
        print(f"   ✅ Attached — active tab: {controller.page.url}\n")

        # 6. Run the task
        result = controller.run_task(task)

    except ChromeLaunchError as e:
        print()
        print(_red("❌ Chrome Launch Error"))
        print(f"   {e}")
        print()
        print("   Fixes:")
        print("     • Close ALL Chrome windows and retry.")
        print("     • Verify CHROME_PATH in .env points to chrome.exe")
        sys.exit(1)

    except AllKeysExhaustedError:
        print()
        print(_yellow("⚠️  All Gemini keys exhausted."))
        print("   Please wait a few minutes or add more keys to .env")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user.")
        sys.exit(0)

    finally:
        # Always stop Playwright (does NOT close Chrome)
        try:
            controller.stop()
        except Exception:
            pass

    # 7. Summary
    duration = time.time() - start_time
    steps = result.get("steps", [])
    final_url = result.get("final_url", "")
    success = result.get("success", False)

    print()
    print("─" * 65)
    print(_bold("📊 TASK SUMMARY"))
    print(f"   Steps taken : {len(steps)}")
    print(f"   Duration    : {duration:.1f}s")
    print(f"   Final URL   : {final_url}")

    if success:
        last_msg = ""
        if steps:
            last_msg = steps[-1]["action"].get("message", "")
        print(f"   Status      : {_green('✅ SUCCESS')}")
        if last_msg:
            print(f"   Message     : {last_msg}")
    else:
        last_reason = ""
        if steps:
            last_action = steps[-1]["action"]
            if last_action.get("action") == "failed":
                last_reason = last_action.get("reason", "Unknown")
            else:
                last_reason = "Max steps reached without terminal action."
        print(f"   Status      : {_red('❌ FAILED')}")
        if last_reason:
            print(f"   Reason      : {last_reason}")

    print("─" * 65)
    print(f"   Session log : logs/browser_session_*.log")
    print()


if __name__ == "__main__":
    main()
