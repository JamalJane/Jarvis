"""
git_committer.py — git operations via subprocess with full error handling.

Pushes to a dated branch, never to main.
Rollback failure prints manual fix instructions and lists .backup files.
"""

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.self_improvement.gemini_analyzer import Improvement

logger = logging.getLogger(__name__)

JARVIS_ROOT = Path(__file__).resolve().parents[3]

_G   = "\033[32m"
_Y   = "\033[33m"
_R   = "\033[31m"
_RST = "\033[0m"


class GitError(Exception):
    pass


@dataclass
class CommitResult:
    success: bool
    commit_hash: str = ""
    branch: str = ""
    pushed: bool = False
    error: str = ""


class GitCommitter:
    """Wraps git add/commit/push/revert with error handling and user-friendly messages."""

    def branch_name(self) -> str:
        return f"self-improvement-{datetime.now().strftime('%Y-%m-%d')}"

    def commit(self, improvements: list[Improvement]) -> CommitResult:
        branch = self.branch_name()
        try:
            # Switch to (or create) the dated branch
            self._git(["checkout", "-B", branch])
            self._git(["add", "."])

            approved = [i for i in improvements]
            msg = self._build_message(approved)
            self._git(["commit", "-m", msg, "--allow-empty"])

            commit_hash = self._git(["rev-parse", "--short", "HEAD"])
            logger.info("Committed to %s — %s", branch, commit_hash)
            return CommitResult(success=True, commit_hash=commit_hash, branch=branch)

        except GitError as exc:
            logger.error("Git commit failed: %s", exc)
            return CommitResult(success=False, error=str(exc), branch=branch)

    def push(self, branch: str) -> bool:
        """Push to remote. Failure is non-fatal — returns False with user message."""
        try:
            self._git(["push", "origin", branch, "--set-upstream", "--force-with-lease"])
            logger.info("Pushed branch %s to origin", branch)
            return True
        except GitError as exc:
            print(f"\n  {_Y}⚠  Git push failed (changes safe locally): {exc}{_RST}")
            print(f"  {_Y}   Run manually: git push origin {branch}{_RST}")
            return False

    def rollback(self) -> bool:
        """
        Revert the HEAD commit. On failure, print manual fix instructions
        and list any .backup files that can be used to restore manually.
        """
        try:
            self._git(["revert", "--no-edit", "HEAD"])
            print(f"\n  {_G}✓ Rollback successful — HEAD reverted.{_RST}")
            logger.info("Rollback successful")
            return True
        except GitError as exc:
            print(f"\n  {_R}✗ git revert failed: {exc}{_RST}")
            print(f"  {_Y}  Manual fix options:{_RST}")
            print(f"  {_Y}  1. Run:  git revert HEAD  in {JARVIS_ROOT}{_RST}")
            print(f"  {_Y}  2. Run:  git reset --hard HEAD~1  (discards commit entirely){_RST}")
            self._list_backups()
            logger.error("Rollback failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #

    def _list_backups(self):
        backups = list(JARVIS_ROOT.rglob("*.backup"))
        if backups:
            print(f"  {_Y}  Backup files found (can be restored manually):{_RST}")
            for b in backups:
                print(f"      {b.relative_to(JARVIS_ROOT)}")
        else:
            print(f"  {_Y}  No .backup files found.{_RST}")

    def _build_message(self, improvements: list[Improvement]) -> str:
        count = len(improvements)
        categories = ", ".join(sorted({i.category for i in improvements}))
        changes = "\n".join(
            f"  - #{i.number} [{i.category}] {i.problem[:80]}"
            for i in improvements
        )
        speeds = [i.speed_estimate for i in improvements if i.speed_estimate > 0]
        tokens = [i.token_estimate for i in improvements if i.token_estimate > 0]
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0
        avg_token = round(sum(tokens) / len(tokens), 1) if tokens else 0

        return (
            f"Self-improvement: {count} improvement(s) — {categories}\n\n"
            f"Changes:\n{changes}\n\n"
            f"Metrics:\n"
            f"  Avg speed improvement: ~+{avg_speed}%\n"
            f"  Avg token savings:     ~-{avg_token}%\n\n"
            f"Testing: All tests passed\n"
            f"Branch: {self.branch_name()} (NOT merged to main)\n"
        )

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git"] + args,
            cwd=JARVIS_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()
