#!/usr/bin/env python3
"""JARVIS - Autonomous AI Assistant & Screen Automation Agent"""

import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root before anything else reads env vars
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

def main():
    from jarvis.main_loop import main as cli_main

    try:
        cli_main()
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    main()
