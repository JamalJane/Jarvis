"""
session_logger.py — writes a timestamped session log to disk and stores a summary in Pinecone.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from jarvis.self_improvement.gemini_analyzer import Improvement
from jarvis.self_improvement.metrics_baseline import MetricsDelta

logger = logging.getLogger(__name__)

LOG_FILE = Path(__file__).resolve().parents[3] / "logs" / "self-improvements.log"

_G   = "\033[32m"
_R   = "\033[31m"
_DIM = "\033[2m"
_RST = "\033[0m"


@dataclass
class SessionReport:
    start_time: str
    end_time: str
    duration_seconds: float
    total_identified: int
    total_approved: int
    total_rejected: int
    delta: Optional[MetricsDelta]
    commit_hash: str
    branch: str
    improvements: List[dict]      # serialisable dicts


class SessionLogger:
    def log_session(self, report: SessionReport, pinecone=None):
        self._print_summary(report)
        self._write_file(report)
        if pinecone:
            self._store_pinecone(report, pinecone)

    # ------------------------------------------------------------------ #

    def _print_summary(self, r: SessionReport):
        delta = r.delta
        print(f"\n{'─' * 50}")
        print(f"  Self-Improvement Session Complete")
        print(f"{'─' * 50}")
        print(f"  Improvements identified: {r.total_identified}")
        print(f"  Approved: {_G}{r.total_approved}{_RST}   Rejected: {_R}{r.total_rejected}{_RST}")
        if delta and delta.measured:
            speed_col = _G if delta.speed_delta_pct > 0 else _R
            token_col = _G if delta.token_delta_pct < 0 else _R
            print(f"  Speed delta:  {speed_col}{delta.speed_delta_pct:+.1f}%{_RST}")
            print(f"  Token delta:  {token_col}{delta.token_delta_pct:+.1f}%{_RST}")
            print(f"  Error delta:  {delta.error_delta:+d}")
        else:
            print(f"  {_DIM}Metrics delta: not measured (no baseline){_RST}")
        if r.commit_hash:
            print(f"  Commit: {r.commit_hash}  (branch: {r.branch})")
        print(f"  Duration: {r.duration_seconds:.0f}s")
        print(f"{'─' * 50}\n")

    def _write_file(self, r: SessionReport):
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"\n[{r.start_time}] SELF-IMPROVEMENT SESSION STARTED",
            f"[{r.end_time}] Duration: {r.duration_seconds:.0f}s",
            f"[{r.end_time}] Improvements identified: {r.total_identified}",
            f"[{r.end_time}] Approved: {r.total_approved}  Rejected: {r.total_rejected}",
        ]
        if r.delta and r.delta.measured:
            lines.append(
                f"[{r.end_time}] Delta — speed: {r.delta.speed_delta_pct:+.1f}%,"
                f" tokens: {r.delta.token_delta_pct:+.1f}%,"
                f" errors: {r.delta.error_delta:+d}"
            )
        if r.commit_hash:
            lines.append(f"[{r.end_time}] Committed: {r.commit_hash} ({r.branch})")
        lines.append(f"[{r.end_time}] SELF-IMPROVEMENT SESSION COMPLETE")

        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        logger.info("Session log written to %s", LOG_FILE)

    def _store_pinecone(self, r: SessionReport, pinecone):
        try:
            from jarvis.memory.pinecone_store import ActionRecord
            description = (
                f"Self-improvement: {r.total_approved} approved, "
                f"{r.total_rejected} rejected"
            )
            record = ActionRecord(
                action_type="self_improvement",
                action_target=r.commit_hash or "no-commit",
                success=r.total_approved > 0,
                task_type="self_improvement",
                timestamp=time.time(),
                execution_duration=r.duration_seconds,
            )
            pinecone.store_action(record)
            logger.info("Session stored in Pinecone")
        except Exception as exc:
            logger.warning("Failed to store session in Pinecone: %s", exc)
