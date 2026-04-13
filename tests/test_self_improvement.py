"""
test_self_improvement.py — unit tests for the self-improvement subsystem.
"""

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_improvement(**kwargs):
    from jarvis.self_improvement.gemini_analyzer import Improvement
    defaults = dict(
        number=1,
        category="Performance",
        severity="Medium",
        file_path="jarvis/core/task_manager.py",
        current_code="old code",
        proposed_code="new code",
        problem="Too slow",
        reasoning="Cache it",
        risk_level="Low",
        speed_estimate=15.0,
        token_estimate=10.0,
    )
    defaults.update(kwargs)
    return Improvement(**defaults)


# ---------------------------------------------------------------------------
# code_analyzer
# ---------------------------------------------------------------------------

class TestCodeAnalyzer:
    def test_whitelist_allows_task_manager(self):
        from jarvis.self_improvement.code_analyzer import CodeAnalyzer
        ca = CodeAnalyzer()
        assert ca.is_modifiable("jarvis/core/task_manager.py")

    def test_whitelist_blocks_self_improvement_dir(self):
        from jarvis.self_improvement.code_analyzer import CodeAnalyzer
        ca = CodeAnalyzer()
        assert not ca.is_modifiable("jarvis/self_improvement/agent.py")

    def test_whitelist_blocks_constants_file(self):
        from jarvis.self_improvement.code_analyzer import CodeAnalyzer
        ca = CodeAnalyzer()
        assert not ca.is_modifiable("jarvis/config/constants.py")

    def test_read_codebase_returns_dict(self):
        from jarvis.self_improvement.code_analyzer import CodeAnalyzer
        ca = CodeAnalyzer()
        # Read whatever files exist on disk — should return a dict
        result = ca.read_codebase()
        assert isinstance(result, dict)
        # Keys should be strings (relative paths)
        for k in result:
            assert isinstance(k, str)

    def test_collect_metrics_empty_history(self):
        from jarvis.self_improvement.code_analyzer import CodeAnalyzer, CodeMetrics
        ca = CodeAnalyzer()
        m = ca.collect_metrics([])
        assert isinstance(m, CodeMetrics)
        assert m.avg_task_time_ms == 0.0
        assert m.failed_task_count == 0


# ---------------------------------------------------------------------------
# gemini_analyzer — parsing
# ---------------------------------------------------------------------------

RAW_RESPONSE = """
Some preamble text.

---IMPROVEMENT 1---
CATEGORY: Performance
SEVERITY: Medium
LOCATION: jarvis/core/task_manager.py:42

CURRENT CODE:
```python
old_function()
```

PROBLEM:
This is too slow.

PROPOSED FIX:
```python
fast_function()
```

REASONING:
Because caching.

ESTIMATED IMPACT:
- Speed improvement: 15%
- Token savings: 10%
- Risk level: Low
---END IMPROVEMENT---

---IMPROVEMENT 2---
CATEGORY: Bug
SEVERITY: High
LOCATION: jarvis/self_improvement/agent.py

CURRENT CODE:
```python
broken()
```

PROBLEM:
Circular dependency risk.

PROPOSED FIX:
```python
fixed()
```

REASONING:
This would break the self-improvement loop.

ESTIMATED IMPACT:
- Speed improvement: 5%
- Token savings: 2%
- Risk level: High
---END IMPROVEMENT---

SUMMARY:
- Total improvements identified: 2
"""


class TestGeminiAnalyzer:
    def test_parse_extracts_one_valid_improvement(self):
        from jarvis.self_improvement.gemini_analyzer import GeminiAnalyzer
        ga = GeminiAnalyzer()
        improvements = ga._parse_response(RAW_RESPONSE)
        # Improvement #2 targets self_improvement/ — should be dropped
        assert len(improvements) == 1
        imp = improvements[0]
        assert imp.number == 1
        assert imp.category == "Performance"
        assert imp.file_path == "jarvis/core/task_manager.py"
        assert imp.risk_level == "Low"
        assert imp.speed_estimate == 15.0

    def test_parse_drops_blacklisted_file(self):
        from jarvis.self_improvement.gemini_analyzer import GeminiAnalyzer
        ga = GeminiAnalyzer()
        improvements = ga._parse_response(RAW_RESPONSE)
        paths = [i.file_path for i in improvements]
        assert "jarvis/self_improvement/agent.py" not in paths

    def test_build_prompt_contains_whitelist(self):
        from jarvis.self_improvement.gemini_analyzer import GeminiAnalyzer
        from jarvis.self_improvement.code_analyzer import CodeMetrics
        ga = GeminiAnalyzer()
        prompt = ga.build_prompt({"jarvis/main_loop.py": "# code"}, CodeMetrics())
        assert "jarvis/self_improvement" in prompt  # mentioned as constraint
        assert "jarvis/core/task_manager.py" in prompt  # in whitelist


# ---------------------------------------------------------------------------
# improvement_ranker
# ---------------------------------------------------------------------------

class TestImprovementRanker:
    def test_low_risk_ranked_before_high_risk(self):
        from jarvis.self_improvement.improvement_ranker import ImprovementRanker
        low  = _make_improvement(number=1, risk_level="Low",  speed_estimate=10)
        high = _make_improvement(number=2, risk_level="High", speed_estimate=50)
        ranker = ImprovementRanker()
        ranked = ranker.rank([high, low])
        assert ranked[0].risk_level == "Low"

    def test_higher_impact_wins_among_same_risk(self):
        from jarvis.self_improvement.improvement_ranker import ImprovementRanker
        a = _make_improvement(number=1, risk_level="Low", speed_estimate=5,  token_estimate=5)
        b = _make_improvement(number=2, risk_level="Low", speed_estimate=30, token_estimate=20)
        ranker = ImprovementRanker()
        ranked = ranker.rank([a, b])
        assert ranked[0].number == 2


# ---------------------------------------------------------------------------
# sandbox_tester
# ---------------------------------------------------------------------------

class TestSandboxTester:
    def test_rejects_blacklisted_file(self):
        from jarvis.self_improvement.sandbox_tester import SandboxTester
        tester = SandboxTester()
        imp = _make_improvement(file_path="jarvis/self_improvement/agent.py")
        result = tester.test_improvement(imp)
        assert not result.approved
        assert "whitelist" in result.reason.lower()

    def test_rejects_high_risk_without_approval(self):
        from jarvis.self_improvement.sandbox_tester import SandboxTester
        tester = SandboxTester()
        imp = _make_improvement(risk_level="High")
        result = tester.test_improvement(imp)
        assert not result.approved
        assert "High-risk" in result.reason

    def test_runs_pytest_on_valid_improvement(self, tmp_path):
        from jarvis.self_improvement.sandbox_tester import SandboxTester, JARVIS_ROOT
        tester = SandboxTester()
        # Create a fake target file
        fake_file = JARVIS_ROOT / "jarvis/core/task_manager.py"
        if not fake_file.exists():
            pytest.skip("task_manager.py not found on disk")

        imp = _make_improvement(
            file_path="jarvis/core/task_manager.py",
            current_code="",   # empty current_code -> patch won't apply -> rejected
            proposed_code="new code",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = tester.test_improvement(imp)
        # Should fail because current_code not found in file
        assert not result.approved


# ---------------------------------------------------------------------------
# high_risk_approval
# ---------------------------------------------------------------------------

class TestHighRiskApprovalUI:
    def test_yes_input_returns_true(self, monkeypatch):
        from jarvis.self_improvement.high_risk_approval import HighRiskApprovalUI
        monkeypatch.setattr("builtins.input", lambda: "yes")
        ui = HighRiskApprovalUI()
        imp = _make_improvement(risk_level="High")
        assert ui.prompt(imp) is True

    def test_no_input_returns_false(self, monkeypatch):
        from jarvis.self_improvement.high_risk_approval import HighRiskApprovalUI
        monkeypatch.setattr("builtins.input", lambda: "no")
        ui = HighRiskApprovalUI()
        imp = _make_improvement(risk_level="High")
        assert ui.prompt(imp) is False


# ---------------------------------------------------------------------------
# rate_limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_run_when_no_lock_file(self, tmp_path, monkeypatch):
        from jarvis.self_improvement import rate_limiter as rl_mod
        monkeypatch.setattr(rl_mod, "LOCK_FILE", tmp_path / ".last_run")
        monkeypatch.setattr(rl_mod, "MIN_INTERVAL_DAYS", 7)
        from jarvis.self_improvement.rate_limiter import RateLimiter
        rl = RateLimiter()
        assert rl.can_run() is True

    def test_blocks_within_interval(self, tmp_path, monkeypatch):
        import importlib
        from datetime import datetime, timedelta
        from jarvis.self_improvement import rate_limiter as rl_mod
        lock = tmp_path / ".last_run"
        lock.write_text((datetime.now() - timedelta(days=1)).isoformat())
        monkeypatch.setattr(rl_mod, "LOCK_FILE", lock)
        monkeypatch.setattr(rl_mod, "MIN_INTERVAL_DAYS", 7)
        from jarvis.self_improvement.rate_limiter import RateLimiter
        rl = RateLimiter()
        assert rl.can_run() is False

    def test_allows_after_interval(self, tmp_path, monkeypatch):
        from datetime import datetime, timedelta
        from jarvis.self_improvement import rate_limiter as rl_mod
        lock = tmp_path / ".last_run"
        lock.write_text((datetime.now() - timedelta(days=8)).isoformat())
        monkeypatch.setattr(rl_mod, "LOCK_FILE", lock)
        monkeypatch.setattr(rl_mod, "MIN_INTERVAL_DAYS", 7)
        from jarvis.self_improvement.rate_limiter import RateLimiter
        rl = RateLimiter()
        assert rl.can_run() is True


# ---------------------------------------------------------------------------
# session_lock
# ---------------------------------------------------------------------------

class TestSessionLock:
    def test_acquire_then_is_active(self, tmp_path, monkeypatch):
        from jarvis.self_improvement import session_lock as sl_mod
        monkeypatch.setattr(sl_mod, "LOCK_FILE", tmp_path / ".active")
        from jarvis.self_improvement.session_lock import SessionLock
        lock = SessionLock()
        assert lock.acquire() is True
        assert lock.is_active() is True
        lock.release()
        assert lock.is_active() is False

    def test_double_acquire_fails(self, tmp_path, monkeypatch):
        from jarvis.self_improvement import session_lock as sl_mod
        monkeypatch.setattr(sl_mod, "LOCK_FILE", tmp_path / ".active")
        from jarvis.self_improvement.session_lock import SessionLock
        lock = SessionLock()
        assert lock.acquire() is True
        assert lock.acquire() is False
        lock.release()


# ---------------------------------------------------------------------------
# metrics_baseline
# ---------------------------------------------------------------------------

class TestMetricsBaseline:
    def test_capture_before_writes_json(self, tmp_path, monkeypatch):
        from jarvis.self_improvement import metrics_baseline as mb_mod
        monkeypatch.setattr(mb_mod, "BASELINE_FILE", tmp_path / "metrics.json")
        from jarvis.self_improvement.metrics_baseline import MetricsBaseline
        from jarvis.self_improvement.code_analyzer import CodeMetrics
        mb = MetricsBaseline()
        mb.capture_before(CodeMetrics(avg_task_time_ms=1000))
        data = json.loads((tmp_path / "metrics.json").read_text())
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["before"]["avg_task_time_ms"] == 1000

    def test_compute_delta_speed(self, tmp_path, monkeypatch):
        from jarvis.self_improvement import metrics_baseline as mb_mod
        monkeypatch.setattr(mb_mod, "BASELINE_FILE", tmp_path / "metrics.json")
        from jarvis.self_improvement.metrics_baseline import MetricsBaseline
        from jarvis.self_improvement.code_analyzer import CodeMetrics
        mb = MetricsBaseline()
        before = CodeMetrics(avg_task_time_ms=1000, total_api_calls=100)
        after  = CodeMetrics(avg_task_time_ms=800,  total_api_calls=90)
        mb.capture_before(before)
        delta = mb.capture_after(after)
        assert delta.measured is True
        assert delta.speed_delta_pct == pytest.approx(20.0)  # (1000-800)/1000 * 100


# ---------------------------------------------------------------------------
# git_committer — rollback
# ---------------------------------------------------------------------------

class TestGitCommitter:
    def test_rollback_success(self, capsys):
        from jarvis.self_improvement.git_committer import GitCommitter
        committer = GitCommitter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = committer.rollback()
        assert result is True
        captured = capsys.readouterr()
        assert "Rollback successful" in captured.out

    def test_rollback_failure_prints_manual_instructions(self, capsys):
        from jarvis.self_improvement.git_committer import GitCommitter
        committer = GitCommitter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="nothing to revert"
            )
            result = committer.rollback()
        assert result is False
        captured = capsys.readouterr()
        assert "Manual fix" in captured.out or "git revert" in captured.out


# ---------------------------------------------------------------------------
# session_logger
# ---------------------------------------------------------------------------

class TestSessionLogger:
    def test_writes_log_file(self, tmp_path, monkeypatch):
        from jarvis.self_improvement import session_logger as sl_mod
        log_path = tmp_path / "self-improvements.log"
        monkeypatch.setattr(sl_mod, "LOG_FILE", log_path)
        from jarvis.self_improvement.session_logger import SessionLogger, SessionReport
        from jarvis.self_improvement.metrics_baseline import MetricsDelta
        sl = SessionLogger()
        report = SessionReport(
            start_time="2026-04-11T20:00:00",
            end_time="2026-04-11T20:03:00",
            duration_seconds=180,
            total_identified=8,
            total_approved=7,
            total_rejected=1,
            delta=MetricsDelta(speed_delta_pct=18.0, token_delta_pct=-9.5, measured=True),
            commit_hash="abc123",
            branch="self-improvement-2026-04-11",
            improvements=[],
        )
        sl.log_session(report, pinecone=None)
        log_text = log_path.read_text()
        assert "SELF-IMPROVEMENT SESSION STARTED" in log_text
        assert "7" in log_text   # approved count
