from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RESUME_FILE = PROJECT_ROOT / "resume.json"
LOG_DIR = PROJECT_ROOT / "logs"

API_KEYS = [
    "GEMINI_KEY_1",
    "GEMINI_KEY_2",
    "GEMINI_KEY_3",
    "GEMINI_KEY_4",
]

DAILY_RESET_HOUR = 0
DAILY_RESET_TZ = "EST"

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2

CONFIDENCE_THRESHOLD = 0.85
SCREENSHOT_COMPRESSION = 50

BLACKLIST = [
    "delete_files",
    "format_disk",
    "regedit",
    "system32_modify",
]

DAILY_REQUEST_LIMIT = 2000
