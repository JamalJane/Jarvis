import logging
import subprocess
import sys
import os

logger = logging.getLogger(__name__)


def launch_jarvis():
    logger.info("Hotkey activated - launching JARVIS")
    jarvis_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jarvis.py")
    subprocess.Popen(
        [sys.executable, jarvis_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )


def start_daemon():
    try:
        from pynput import keyboard
    except ImportError:
        logger.error("pynput not installed. Run: pip install pynput")
        print("ERROR: pynput not installed")
        print("Run: pip install pynput")
        return

    def on_activate():
        launch_jarvis()

    print("JARVIS Daemon started...")
    print("Press Ctrl+Alt+J to launch JARVIS")
    print("Press Ctrl+C to exit")

    with keyboard.GlobalHotKeys({
        '<ctrl>+<alt>+j': on_activate
    }) as h:
        h.join()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    start_daemon()
