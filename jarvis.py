#!/usr/bin/env python3
"""JARVIS - Autonomous AI Assistant & Screen Automation Agent"""

import logging
import os
import sys
from pathlib import Path

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/jarvis.log"),
        logging.StreamHandler()
    ]
)


def main():
    from jarvis.main_loop import Jarvis

    jarvis = Jarvis()
    try:
        jarvis.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        jarvis.cleanup()


if __name__ == "__main__":
    main()
