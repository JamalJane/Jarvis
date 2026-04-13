"""
metrics_dashboard.py — reads metrics.json and self-improvements.log to print an ASCII table.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASELINE_FILE = Path(__file__).resolve().parents[3] / "logs" / "metrics.json"
LOG_FILE      = Path(__file__).resolve().parents[3] / "logs" / "self-improvements.log"

_G   = "\033[32m"
_Y   = "\033[33m"
_R   = "\033[31m"
_DIM = "\033[2m"
_RST = "\033[0m"


class MetricsDashboard:
    """Read the persistent metrics store and display a trend table."""

    def display(self):
        sessions = self._load_sessions()
        if not sessions:
            print(f"\n  {_DIM}No self-improvement sessions recorded yet.{_RST}\n")
            print(f"  {_DIM}Run /optimize to start a session.{_RST}\n")
            return

        header = f"{'Date':<22} {'Imps':>5} {'App':>5} {'Speed Δ':>9} {'Token Δ':>9} {'Commit':<12}"
        sep    = "─" * len(header)

        print(f"\n  Self-Improvement History")
        print(f"  {sep}")
        print(f"  {header}")
        print(f"  {sep}")

        for s in sessions:
            date  = s.get("date", "")[:16]
            delta = s.get("delta") or {}
            speed = delta.get("speed_delta_pct", None)
            token = delta.get("token_delta_pct", None)
            imp   = s.get("improvements_identified", "?")
            app   = s.get("improvements_applied", "?")
            commit = s.get("commit_hash", "")[:10] or "—"

            speed_str = (f"{_G}{speed:+.1f}%{_RST}" if speed and speed > 0
                         else f"{_R}{speed:+.1f}%{_RST}" if speed else f"{_DIM}—{_RST}")
            token_str = (f"{_G}{token:+.1f}%{_RST}" if token and token < 0
                         else f"{_R}{token:+.1f}%{_RST}" if token else f"{_DIM}—{_RST}")

            print(f"  {date:<22} {str(imp):>5} {str(app):>5} {speed_str:>9} {token_str:>9} {commit:<12}")

        print(f"  {sep}\n")

        # Also tail the log file
        self._print_log_tail(10)

    # ------------------------------------------------------------------ #

    def _load_sessions(self) -> list[dict]:
        if not BASELINE_FILE.exists():
            return []
        try:
            data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
            return data.get("sessions", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("metrics.json unreadable: %s", exc)
            return []

    def _print_log_tail(self, lines: int):
        if not LOG_FILE.exists():
            return
        try:
            all_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
            tail = all_lines[-lines:]
            print(f"  {_DIM}Recent log entries:{_RST}")
            for line in tail:
                print(f"  {_DIM}{line}{_RST}")
            print()
        except OSError:
            pass
