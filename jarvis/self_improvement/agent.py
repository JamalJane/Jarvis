"""
agent.py — SelfImprovementAgent orchestrator.

Runs the complete 7-phase self-improvement pipeline:
  1. Read codebase + collect metrics
  2. Capture metrics baseline (before)
  3. Send to Gemini for analysis
  4. Rank improvements
  5. For each improvement: prompt for High-risk, sandbox-test, apply
  6. Capture metrics baseline (after) + compute delta
  7. Git commit + push + log session

Also provides:
  - run_analysis_only()     — analysis + ranking, no file changes
  - rollback_last_commit()  — git revert HEAD with error handling
  - show_history()          — ASCII metrics dashboard
  - disable_auto/enable_auto — toggle flag
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from jarvis.self_improvement.code_analyzer import CodeAnalyzer, CodeMetrics
from jarvis.self_improvement.gemini_analyzer import GeminiAnalyzer, Improvement
from jarvis.self_improvement.high_risk_approval import HighRiskApprovalUI
from jarvis.self_improvement.improvement_applicator import ImprovementApplicator
from jarvis.self_improvement.improvement_ranker import ImprovementRanker
from jarvis.self_improvement.metrics_baseline import MetricsBaseline, MetricsDelta
from jarvis.self_improvement.metrics_dashboard import MetricsDashboard
from jarvis.self_improvement.git_committer import GitCommitter
from jarvis.self_improvement.rate_limiter import RateLimiter
from jarvis.self_improvement.sandbox_tester import SandboxTester
from jarvis.self_improvement.session_lock import SessionLock
from jarvis.self_improvement.session_logger import SessionLogger, SessionReport

logger = logging.getLogger(__name__)

_G   = "\033[32m"
_Y   = "\033[33m"
_R   = "\033[31m"
_DIM = "\033[2m"
_B   = "\033[1m"
_RST = "\033[0m"


class SelfImprovementAgent:
    def __init__(self):
        self.auto_enabled    = True
        self.analyzer        = CodeAnalyzer()
        self.gemini          = GeminiAnalyzer()
        self.ranker          = ImprovementRanker()
        self.tester          = SandboxTester()
        self.applicator      = ImprovementApplicator()
        self.baseline        = MetricsBaseline()
        self.committer       = GitCommitter()
        self.rate_limiter    = RateLimiter()
        self.session_lock    = SessionLock()
        self.logger_         = SessionLogger()
        self.dashboard       = MetricsDashboard()
        self.approval_ui     = HighRiskApprovalUI()

    # ------------------------------------------------------------------ #
    # PUBLIC API                                                            #
    # ------------------------------------------------------------------ #

    def run_session(self, task_history: list[dict], api_manager, pinecone=None):
        """Full self-improvement pipeline. Blocks until complete."""
        start = time.time()
        start_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # --- Guard checks ---
        if not self.rate_limiter.can_run():
            print(
                f"\n  {_Y}Self-improvement skipped — last run: {self.rate_limiter.last_run_str()}"
                f" (min interval: 7 days).{_RST}"
                f"\n  {_DIM}Override: /improvements-on then /optimize{_RST}\n"
            )
            return

        if not self.session_lock.acquire():
            print(f"\n  {_Y}Cannot start: session lock is held (another task is active).{_RST}\n")
            return

        try:
            self._run_pipeline(task_history, api_manager, pinecone, start, start_str)
        finally:
            self.session_lock.release()
            self.rate_limiter.mark_run()

    def run_analysis_only(self, task_history: list[dict], api_manager):
        """Analyse + rank improvements. No file changes, no git."""
        print(f"\n  {_Y}Analysing codebase (read-only)...{_RST}\n")
        sources = self.analyzer.read_codebase()
        metrics = self.analyzer.collect_metrics(task_history, api_manager)
        print(f"  ✓ Read {len(sources)} files ({metrics.lines_of_code:,} lines)")

        improvements = self.gemini.analyze(api_manager, sources, metrics)
        ranked       = self.ranker.rank(improvements)

        print(f"  ✓ {len(ranked)} improvements identified (no changes applied)\n")
        for i, imp in enumerate(ranked, 1):
            risk_col = _R if imp.risk_level == "High" else (_Y if imp.risk_level == "Medium" else _G)
            print(
                f"  [{i}] #{imp.number} {_B}{imp.category}{_RST} | "
                f"{risk_col}{imp.risk_level} risk{_RST} | "
                f"{imp.file_path}\n"
                f"      {_DIM}{imp.problem[:100]}{_RST}"
            )
        print()

    def rollback_last_commit(self) -> bool:
        """Revert HEAD with error handling. Returns True on success."""
        return self.committer.rollback()

    def show_history(self):
        """Print the ASCII metrics dashboard."""
        self.dashboard.display()

    def disable_auto(self):
        self.auto_enabled = False
        logger.info("Auto self-improvement disabled")

    def enable_auto(self):
        self.auto_enabled = True
        logger.info("Auto self-improvement enabled")

    # ------------------------------------------------------------------ #
    # PIPELINE                                                              #
    # ------------------------------------------------------------------ #

    def _run_pipeline(
        self,
        task_history: list[dict],
        api_manager,
        pinecone,
        start: float,
        start_str: str,
    ):
        print(f"\n  {_B}╔══ Jarvis Self-Improvement ══╗{_RST}")

        # Phase 1: Read codebase
        print(f"\n  {_Y}Phase 1/7 — Reading codebase...{_RST}")
        sources = self.analyzer.read_codebase()
        metrics_before = self.analyzer.collect_metrics(task_history, api_manager)
        print(f"  ✓ {len(sources)} files · {metrics_before.lines_of_code:,} lines")

        # Phase 2: Capture baseline
        print(f"  {_Y}Phase 2/7 — Capturing metrics baseline...{_RST}")
        self.baseline.capture_before(metrics_before)
        print(f"  ✓ Baseline recorded (avg task: {metrics_before.avg_task_time_ms:.0f}ms)")

        # Phase 3: Gemini analysis
        print(f"  {_Y}Phase 3/7 — Sending to Gemini for analysis...{_RST}")
        improvements = self.gemini.analyze(api_manager, sources, metrics_before)
        ranked       = self.ranker.rank(improvements)
        print(f"  ✓ {len(ranked)} improvements identified")

        # Phase 4–5: Test + apply
        print(f"  {_Y}Phase 4–5/7 — Testing and applying improvements...{_RST}\n")
        approved_list, rejected_list = self._apply_improvements(ranked, task_history, api_manager)

        # Phase 6: Capture after-metrics
        print(f"  {_Y}Phase 6/7 — Measuring results...{_RST}")
        metrics_after = self.analyzer.collect_metrics(task_history, api_manager)
        delta = self.baseline.capture_after(metrics_after)

        # Phase 7: Git + log
        print(f"  {_Y}Phase 7/7 — Committing and logging...{_RST}")
        commit_result = self.committer.commit(approved_list)
        if commit_result.success:
            self.committer.push(commit_result.branch)

        end_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        report = SessionReport(
            start_time=start_str,
            end_time=end_str,
            duration_seconds=round(time.time() - start, 1),
            total_identified=len(ranked),
            total_approved=len(approved_list),
            total_rejected=len(rejected_list),
            delta=delta,
            commit_hash=commit_result.commit_hash,
            branch=commit_result.branch,
            improvements=[
                {
                    "number": i.number,
                    "category": i.category,
                    "risk_level": i.risk_level,
                    "file": i.file_path,
                    "approved": i in approved_list,
                }
                for i in ranked
            ],
        )
        self.logger_.log_session(report, pinecone)

    def _apply_improvements(
        self,
        ranked: list[Improvement],
        task_history: list[dict],
        api_manager,
    ) -> tuple[list[Improvement], list[Improvement]]:
        approved: list[Improvement] = []
        rejected: list[Improvement] = []
        total = len(ranked)

        for idx, imp in enumerate(ranked, 1):
            bar_filled = int(20 * idx / total)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            risk_col = _R if imp.risk_level == "High" else (_Y if imp.risk_level == "Medium" else _G)
            print(
                f"  [{bar}] {idx}/{total} #{imp.number} "
                f"{risk_col}{imp.risk_level}{_RST} {imp.category} — {imp.file_path}"
            )

            # High-risk: ask user
            if imp.risk_level == "High":
                user_ok = self.approval_ui.prompt(imp)
                if not user_ok:
                    rejected.append(imp)
                    print(f"  {_DIM}  ✗ Skipped (user declined){_RST}")
                    continue
                # User approved high-risk — pass flag to bypass sandbox check (don't mutate imp)
                result = self.tester.test_improvement(imp, user_approved=True)
            else:
                result = self.tester.test_improvement(imp)

            if result.approved:
                self.applicator.apply(imp, result)
                approved.append(imp)
                print(f"  {_G}  ✓ APPROVED — applied{_RST}")
            else:
                rejected.append(imp)
                print(f"  {_R}  ✗ REJECTED — {result.reason}{_RST}")

        return approved, rejected
