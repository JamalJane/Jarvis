"""
rate_limiter.py — enforces a minimum interval between self-improvement sessions.

Set MIN_INTERVAL_DAYS = 0 for pure on-demand (no automatic scheduling).
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_FILE      = Path(__file__).resolve().parents[3] / "logs" / ".last_improvement_run"
MIN_INTERVAL_DAYS = 7   # set to 0 to allow unlimited on-demand runs


class RateLimiter:
    """File-based rate limiter: stores the last run timestamp as ISO 8601 text."""

    def can_run(self) -> bool:
        if MIN_INTERVAL_DAYS == 0:
            return True
        if not LOCK_FILE.exists():
            return True
        try:
            last = datetime.fromisoformat(LOCK_FILE.read_text().strip())
            eligible = last + timedelta(days=MIN_INTERVAL_DAYS)
            if datetime.now() < eligible:
                logger.info(
                    "Rate limit active — next run eligible at %s",
                    eligible.strftime("%Y-%m-%d %H:%M"),
                )
                return False
        except (ValueError, OSError) as exc:
            logger.warning("Rate limiter read error (%s) — allowing run", exc)
        return True

    def mark_run(self):
        """Record the current time as the start of a completed session."""
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.write_text(datetime.now().isoformat())
        logger.info("Rate limiter timestamp updated.")

    def last_run_str(self) -> str:
        if not LOCK_FILE.exists():
            return "never"
        try:
            return LOCK_FILE.read_text().strip()
        except OSError:
            return "unknown"

    def reset(self):
        """Remove the lock file so the next call to can_run() returns True immediately."""
        LOCK_FILE.unlink(missing_ok=True)
        logger.info("Rate limiter reset — next run is unrestricted.")
