"""
session_lock.py — file-based concurrency lock.

Prevents self-improvement from patching files while a task is actively running,
and prevents new tasks from starting while self-improvement is patching.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_FILE = Path(__file__).resolve().parents[3] / "logs" / ".self_improvement_active"


class SessionLock:
    """Single-process file lock. Stores PID of the locking process."""

    def acquire(self) -> bool:
        """
        Returns True if the lock was successfully acquired.
        Returns False if already locked by another holder.
        """
        if LOCK_FILE.exists():
            pid = self._read_pid()
            logger.info("Session lock is held (PID %s)", pid)
            return False
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.write_text(str(os.getpid()))
        logger.info("Session lock acquired (PID %d)", os.getpid())
        return True

    def release(self):
        """Release the lock. Safe to call even if already released."""
        LOCK_FILE.unlink(missing_ok=True)
        logger.info("Session lock released")

    def is_active(self) -> bool:
        """Return True if the lock file exists (another holder is active)."""
        return LOCK_FILE.exists()

    def _read_pid(self) -> str:
        try:
            return LOCK_FILE.read_text().strip()
        except OSError:
            return "unknown"
