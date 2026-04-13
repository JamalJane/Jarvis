"""
code_analyzer.py — reads whitelisted Jarvis source files and collects runtime metrics.

FILE_WHITELIST: files that CAN be modified by self-improvement.
FILE_BLACKLIST_PREFIXES: directory/file prefixes that are permanently read-only.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

JARVIS_ROOT = Path(__file__).resolve().parents[2]   # c:/Users/bashe/jarvis

# Files whose content is sent to Gemini AND that may be patched
FILE_WHITELIST = [
    "jarvis/main_loop.py",
    "jarvis/config/api_manager.py",
    "jarvis/core/task_manager.py",
    "jarvis/memory/pinecone_store.py",
    "jarvis/memory/prediction.py",
    "jarvis/memory/context_selector.py",
    "jarvis/memory/local_store.py",
    "jarvis/memory/context_guard.py",
    "jarvis/flows/retry_logic.py",
    "jarvis/flows/blacklist_action.py",
    "jarvis/flows/resume_task.py",
]

# These are never patched — enforced at both prompt build and parse time
FILE_BLACKLIST_PREFIXES = [
    "jarvis/self_improvement/",   # no circular dependency
    "jarvis/config/constants.py", # API key names
    "jarvis/config/blacklist.py", # security list
]


@dataclass
class CodeMetrics:
    avg_task_time_ms: float = 0.0
    total_api_calls: int = 0
    failed_task_count: int = 0
    lines_of_code: int = 0
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))


class CodeAnalyzer:
    """Reads source files from disk and derives runtime metrics from task history."""

    def is_modifiable(self, file_path: str) -> bool:
        """Return True only if file is whitelisted and not blacklisted."""
        norm = file_path.replace("\\", "/")
        for prefix in FILE_BLACKLIST_PREFIXES:
            if norm.startswith(prefix) or norm == prefix.rstrip("/"):
                return False
        return norm in FILE_WHITELIST

    def read_codebase(self) -> dict[str, str]:
        """Read all whitelisted source files. Missing files are skipped with a warning."""
        sources: dict[str, str] = {}
        for rel_path in FILE_WHITELIST:
            abs_path = JARVIS_ROOT / rel_path
            if abs_path.exists():
                try:
                    sources[rel_path] = abs_path.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.warning("Could not read %s: %s", rel_path, exc)
            else:
                logger.warning("Whitelisted file not found on disk: %s", rel_path)
        total_lines = sum(src.count("\n") for src in sources.values())
        logger.info("Read %d files, %d total lines", len(sources), total_lines)
        return sources

    def collect_metrics(
        self,
        task_history: list[dict],
        api_manager=None,
    ) -> CodeMetrics:
        """Derive CodeMetrics from the last 50 task_history entries."""
        recent = task_history[-50:] if len(task_history) > 50 else task_history

        # Average execution duration (stored by task_manager._log_action via PineconeStore)
        durations = [
            e.get("execution_duration", 0.0)
            for e in recent
            if isinstance(e.get("execution_duration"), (int, float))
        ]
        avg_ms = (sum(durations) / len(durations) * 1000) if durations else 0.0

        # Failed tasks
        failed = sum(1 for e in recent if not e.get("success", True))

        # Total API calls across all tracked keys
        total_calls = 0
        if api_manager is not None:
            try:
                total_calls = sum(api_manager.request_counts.values())
            except AttributeError:
                pass

        # Lines of code
        sources = self.read_codebase()
        loc = sum(src.count("\n") for src in sources.values())

        return CodeMetrics(
            avg_task_time_ms=round(avg_ms, 2),
            total_api_calls=total_calls,
            failed_task_count=failed,
            lines_of_code=loc,
        )
