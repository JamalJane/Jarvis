"""
improvement_applicator.py — applies an approved patch to the live file
and prepends an inline comment documenting the self-improvement.
"""

import logging
from datetime import datetime
from pathlib import Path

from jarvis.self_improvement.gemini_analyzer import Improvement
from jarvis.self_improvement.sandbox_tester import TestResult

logger = logging.getLogger(__name__)

JARVIS_ROOT = Path(__file__).resolve().parents[3]


class ImprovementApplicator:
    """Write the approved patch into the live source file."""

    def apply(self, imp: Improvement, test_result: TestResult) -> bool:
        """
        Replaces imp.current_code with imp.proposed_code in the live file
        and inserts an inline comment block immediately before the new code.

        Returns True on success.
        """
        if not test_result.approved:
            logger.warning("apply() called with unapproved TestResult — skipping")
            return False

        target = JARVIS_ROOT / imp.file_path
        if not target.exists():
            logger.error("Target file disappeared before apply: %s", target)
            return False

        text = target.read_text(encoding="utf-8")

        comment = self._inline_comment(imp)
        replacement = comment + imp.proposed_code

        # current_code should already be in the file (sandbox_tester left it patched)
        # but we re-apply cleanly here in case of edge cases
        if imp.proposed_code in text:
            # Already applied by sandbox_tester; just ensure comment is there
            if comment.strip().splitlines()[0] not in text:
                text = text.replace(imp.proposed_code, replacement, 1)
                target.write_text(text, encoding="utf-8")
                logger.info("Added inline comment to already-applied patch #%d", imp.number)
            return True

        if imp.current_code in text:
            text = text.replace(imp.current_code, replacement, 1)
            target.write_text(text, encoding="utf-8")
            logger.info("Applied improvement #%d to %s", imp.number, imp.file_path)
            return True

        logger.error(
            "Neither current_code nor proposed_code found in %s — improvement #%d skipped",
            imp.file_path, imp.number,
        )
        return False

    # ------------------------------------------------------------------ #

    def _inline_comment(self, imp: Improvement) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        speed_str = f"+{imp.speed_estimate}%" if imp.speed_estimate >= 0 else f"{imp.speed_estimate}%"
        token_str = f"-{imp.token_estimate}%" if imp.token_estimate >= 0 else f"+{abs(imp.token_estimate)}%"
        return (
            f"# SELF-IMPROVEMENT {date}: {imp.category} — improvement #{imp.number}\n"
            f"# Category: {imp.category} | Risk: {imp.risk_level} "
            f"| Expected: {speed_str} speed, {token_str} tokens\n"
        )
