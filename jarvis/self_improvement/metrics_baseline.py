"""
metrics_baseline.py — captures before/after CodeMetrics and persists them to metrics.json.

This is the source of truth for all "% improvement" claims displayed after a session.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from jarvis.self_improvement.code_analyzer import CodeMetrics

logger = logging.getLogger(__name__)

BASELINE_FILE = Path(__file__).resolve().parents[3] / "logs" / "metrics.json"


@dataclass
class MetricsDelta:
    speed_delta_pct: float = 0.0      # positive = faster (good)
    token_delta_pct: float = 0.0      # negative = fewer tokens used (good)
    error_delta: int = 0              # negative = fewer errors (good)
    measured: bool = False            # False when baseline was missing


class MetricsBaseline:
    """
    Workflow:
        baseline.capture_before(metrics)   # call once before first patch
        ...apply improvements...
        delta = baseline.capture_after(metrics)  # call after all patches
    """

    def capture_before(self, metrics: CodeMetrics):
        """Write the 'before' snapshot. Creates or appends a new session entry."""
        data = self._load()
        session = {
            "date": metrics.timestamp,
            "before": asdict(metrics),
            "after": None,
            "delta": None,
        }
        data["sessions"].append(session)
        self._save(data)
        logger.info("Metrics baseline captured (before): %s", asdict(metrics))

    def capture_after(self, metrics: CodeMetrics) -> MetricsDelta:
        """
        Writes the 'after' snapshot to the last open session entry.
        Computes and stores the delta. Returns the MetricsDelta.
        """
        data = self._load()
        if not data["sessions"]:
            logger.warning("capture_after called with no open session")
            return MetricsDelta(measured=False)

        # Find the last session that has no 'after' yet
        last = data["sessions"][-1]
        if last.get("after") is not None:
            logger.warning("Last session already closed; creating new entry")
            last = {"date": metrics.timestamp, "before": None, "after": None, "delta": None}
            data["sessions"].append(last)

        last["after"] = asdict(metrics)
        delta = self._compute_delta(last.get("before"), asdict(metrics))
        last["delta"] = asdict(delta)
        self._save(data)
        logger.info("Metrics baseline captured (after). Delta: %s", asdict(delta))
        return delta

    # ------------------------------------------------------------------ #

    def _compute_delta(self, before: dict | None, after: dict) -> MetricsDelta:
        if not before:
            return MetricsDelta(measured=False)

        before_time  = before.get("avg_task_time_ms", 0.0) or 0.0
        after_time   = after.get("avg_task_time_ms", 0.0) or 0.0
        before_calls = before.get("total_api_calls", 0) or 0
        after_calls  = after.get("total_api_calls", 0) or 0
        before_errs  = before.get("failed_task_count", 0) or 0
        after_errs   = after.get("failed_task_count", 0) or 0

        if before_time > 0:
            speed_pct = round((before_time - after_time) / before_time * 100, 1)
        else:
            speed_pct = 0.0

        if before_calls > 0:
            token_pct = round((after_calls - before_calls) / before_calls * 100, 1)
        else:
            token_pct = 0.0

        return MetricsDelta(
            speed_delta_pct=speed_pct,
            token_delta_pct=token_pct,
            error_delta=after_errs - before_errs,
            measured=True,
        )

    def _load(self) -> dict:
        if BASELINE_FILE.exists():
            try:
                return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("metrics.json corrupt (%s) — starting fresh", exc)
        return {"sessions": []}

    def _save(self, data: dict):
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
