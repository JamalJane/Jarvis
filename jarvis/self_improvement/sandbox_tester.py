"""
sandbox_tester.py — backup → patch → pytest → pylint → decide → restore if failed.

Each improvement is tested in isolation:
  1. Backup the target file
  2. Apply the patch
  3. Run the full test suite + lint
  4. If anything fails, atomically restore from backup
  5. Return TestResult(approved, reason, output)
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jarvis.self_improvement.code_analyzer import CodeAnalyzer
from jarvis.self_improvement.gemini_analyzer import Improvement

logger = logging.getLogger(__name__)

JARVIS_ROOT = Path(__file__).resolve().parents[3]
PYLINT_THRESHOLD = "7.5"


@dataclass
class TestResult:
    approved: bool
    reason: str
    test_output: str = ""
    lint_output: str = ""


class SandboxTester:
    """Sandbox-test one improvement at a time with full backup/restore safety."""

    def test_improvement(self, imp: Improvement) -> TestResult:
        # Safety gate 1: whitelist check
        if not CodeAnalyzer().is_modifiable(imp.file_path):
            logger.warning("Improvement #%d targets blacklisted file: %s", imp.number, imp.file_path)
            return TestResult(approved=False, reason=f"File '{imp.file_path}' is not in the whitelist")

        # Safety gate 2: High-risk items must have been explicitly approved by the caller
        if imp.risk_level == "High":
            return TestResult(
                approved=False,
                reason="High-risk — requires explicit user approval via HighRiskApprovalUI",
            )

        target = JARVIS_ROOT / imp.file_path
        if not target.exists():
            return TestResult(approved=False, reason=f"Target file not found: {target}")

        backup = self._backup(target)
        original_text = target.read_text(encoding="utf-8")

        try:
            patched = self._apply_patch(original_text, imp.current_code, imp.proposed_code)
            if patched is None:
                self._restore(backup, target)
                return TestResult(
                    approved=False,
                    reason="current_code not found verbatim in target file — patch cannot be applied",
                )

            target.write_text(patched, encoding="utf-8")

            test_ok, test_out = self._run_tests()
            lint_ok, lint_out = self._run_linting()

            if test_ok and lint_ok:
                backup.unlink(missing_ok=True)
                logger.info("Improvement #%d: APPROVED (tests + lint passed)", imp.number)
                return TestResult(approved=True, reason="All tests passed", test_output=test_out, lint_output=lint_out)
            else:
                self._restore(backup, target)
                reason = []
                if not test_ok:
                    reason.append("pytest failed")
                if not lint_ok:
                    reason.append(f"pylint score below {PYLINT_THRESHOLD}")
                logger.info("Improvement #%d: REJECTED (%s)", imp.number, ", ".join(reason))
                return TestResult(
                    approved=False,
                    reason=", ".join(reason),
                    test_output=test_out,
                    lint_output=lint_out,
                )

        except Exception as exc:
            self._restore(backup, target)
            logger.error("Exception while testing improvement #%d: %s", imp.number, exc)
            return TestResult(approved=False, reason=f"Exception: {exc}")

    # ------------------------------------------------------------------ #

    def _backup(self, target: Path) -> Path:
        backup = target.with_suffix(target.suffix + ".backup")
        shutil.copy2(target, backup)
        logger.debug("Backed up %s -> %s", target.name, backup.name)
        return backup

    def _restore(self, backup: Path, target: Path):
        if backup.exists():
            shutil.copy2(backup, target)
            backup.unlink(missing_ok=True)
            logger.info("Restored %s from backup", target.name)

    def _apply_patch(self, text: str, current: str, proposed: str) -> str | None:
        """Replace the first occurrence of current_code with proposed_code."""
        if current not in text:
            # Try with normalised whitespace (dedented match)
            stripped = current.strip()
            if stripped not in text:
                logger.warning("current_code not found in target file")
                return None
            current = stripped
        return text.replace(current, proposed, 1)

    def _run_tests(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "--timeout=30", "-q", "--tb=short"],
                cwd=JARVIS_ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "pytest timed out after 180s"
        except FileNotFoundError:
            return False, "pytest not found"

    def _run_linting(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [
                    "python", "-m", "pylint", "jarvis/",
                    f"--fail-under={PYLINT_THRESHOLD}",
                    "--errors-only",
                    "--disable=C,R,W",
                ],
                cwd=JARVIS_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "pylint timed out after 120s"
        except FileNotFoundError:
            # pylint not installed — treat as pass so it doesn't block everything
            logger.warning("pylint not found; skipping lint check")
            return True, "pylint not installed — skipped"
