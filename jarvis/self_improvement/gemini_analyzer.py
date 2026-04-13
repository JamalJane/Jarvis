"""
gemini_analyzer.py — builds the Gemini analysis prompt and parses structured improvements.

Whitelist enforcement is applied at parse time: any improvement targeting a file
not in FILE_WHITELIST is silently dropped.
"""

import logging
import re
from dataclasses import dataclass, field

from jarvis.self_improvement.code_analyzer import (
    FILE_WHITELIST,
    CodeAnalyzer,
    CodeMetrics,
)

logger = logging.getLogger(__name__)

_IMPROVEMENT_START = re.compile(r"---IMPROVEMENT\s+(\d+)---", re.IGNORECASE)
_IMPROVEMENT_END   = re.compile(r"---END IMPROVEMENT---", re.IGNORECASE)

_FIELD_RE = {
    "category":       re.compile(r"CATEGORY:\s*(.+)", re.IGNORECASE),
    "severity":       re.compile(r"SEVERITY:\s*(.+)", re.IGNORECASE),
    "file_path":      re.compile(r"LOCATION:\s*(.+)", re.IGNORECASE),
    "risk_level":     re.compile(r"Risk level:\s*(.+)", re.IGNORECASE),
    "speed_estimate": re.compile(r"Speed improvement:\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE),
    "token_estimate": re.compile(r"Token savings:\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE),
}

_CURRENT_CODE_RE  = re.compile(
    r"CURRENT CODE:\s*\n```(?:python)?\n(.*?)```", re.DOTALL | re.IGNORECASE
)
_PROPOSED_CODE_RE = re.compile(
    r"PROPOSED FIX:\s*\n```(?:python)?\n(.*?)```", re.DOTALL | re.IGNORECASE
)
_PROBLEM_RE  = re.compile(r"PROBLEM:\s*\n(.+?)(?=\n[A-Z]+:|\Z)", re.DOTALL | re.IGNORECASE)
_REASONING_RE = re.compile(r"REASONING:\s*\n(.+?)(?=\n[A-Z]+:|\Z)", re.DOTALL | re.IGNORECASE)


@dataclass
class Improvement:
    number: int
    category: str = "Quality"
    severity: str = "Low"
    file_path: str = ""
    current_code: str = ""
    proposed_code: str = ""
    problem: str = ""
    reasoning: str = ""
    risk_level: str = "Low"
    speed_estimate: float = 0.0
    token_estimate: float = 0.0


class GeminiAnalyzer:
    """Builds the analysis prompt, calls the API, and parses the structured response."""

    # ------------------------------------------------------------------ #
    #  Prompt construction                                                  #
    # ------------------------------------------------------------------ #

    def build_prompt(self, sources: dict[str, str], metrics: CodeMetrics) -> str:
        whitelist_str = "\n".join(f"  - {f}" for f in FILE_WHITELIST)
        source_sections = "\n\n".join(
            f"=== {path} ===\n{code}" for path, code in sources.items()
        )

        return f"""You are JARVIS, an autonomous AI assistant. You are analyzing your own
source code to identify improvements.

CURRENT METRICS:
- Average task time: {metrics.avg_task_time_ms} ms
- Total API calls this session: {metrics.total_api_calls}
- Failed tasks (last 50): {metrics.failed_task_count}
- Lines of code: {metrics.lines_of_code}
- Timestamp: {metrics.timestamp}

MODIFIABLE FILES (you may ONLY suggest changes to files in this list):
{whitelist_str}

CRITICAL CONSTRAINT: You CANNOT suggest changes to:
  - jarvis/self_improvement/ (any file — circular dependency risk)
  - jarvis/config/constants.py
  - jarvis/config/blacklist.py
  - API key storage, authentication, security checks, file permissions, system calls

SOURCE CODE TO ANALYZE:
{source_sections}

ANALYSIS TASK:
Review the code and identify improvements across 5 categories:
1. PERFORMANCE BOTTLENECKS — slow execution, unnecessary API calls, token waste
2. BUGS & EDGE CASES — unhandled exceptions, race conditions, missing fallbacks
3. CODE QUALITY — duplicated logic, overly complex functions, poor naming
4. ALGORITHM IMPROVEMENTS — better confidence thresholds, retry backoff, smarter logic
5. PATTERN OPTIMIZATION — caching opportunities, vector query optimization

RESPONSE FORMAT — for EACH improvement use EXACTLY this format:

---IMPROVEMENT [NUMBER]---
CATEGORY: [Performance/Bug/Quality/Algorithm/Pattern]
SEVERITY: [Critical/High/Medium/Low]
LOCATION: [file path from the modifiable files list, line number if known]

CURRENT CODE:
```python
[exact current code]
```

PROBLEM:
[explanation of what is wrong and why]

PROPOSED FIX:
```python
[improved replacement code]
```

REASONING:
[why this is better]

ESTIMATED IMPACT:
- Speed improvement: [X]%
- Token savings: [X]%
- Risk level: [Low/Medium/High]
---END IMPROVEMENT---

After all improvements, provide a SUMMARY:
- Total improvements identified: [X]
- Estimated total speedup: [X]%
- Estimated token savings: [X]%
- Breaking changes: [Yes/No]
- Safe to auto-apply: [Yes/No]
"""

    # ------------------------------------------------------------------ #
    #  Analysis (API call + parse)                                          #
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        api_manager,
        sources: dict[str, str],
        metrics: CodeMetrics,
    ) -> list[Improvement]:
        prompt = self.build_prompt(sources, metrics)
        logger.info("Sending %d-line prompt to Gemini for self-analysis", prompt.count("\n"))
        raw = api_manager.call_api(prompt)
        logger.info("Received Gemini response (%d chars)", len(raw))
        improvements = self._parse_response(raw)
        logger.info("Parsed %d improvements", len(improvements))
        return improvements

    # ------------------------------------------------------------------ #
    #  Parsing                                                              #
    # ------------------------------------------------------------------ #

    def _parse_response(self, raw: str) -> list[Improvement]:
        analyzer = CodeAnalyzer()
        improvements: list[Improvement] = []

        # Split on improvement blocks
        blocks = re.split(_IMPROVEMENT_START, raw)
        # blocks = [preamble, number1, block1, number2, block2, ...]
        it = iter(blocks[1:])   # skip preamble
        for num_str, block in zip(it, it):
            imp = self._parse_block(int(num_str), block)
            if imp is None:
                continue
            # Whitelist enforcement at parse time
            if not analyzer.is_modifiable(imp.file_path):
                logger.warning(
                    "Improvement #%d targets non-whitelisted file '%s' — dropped",
                    imp.number, imp.file_path,
                )
                continue
            improvements.append(imp)

        return improvements

    def _parse_block(self, number: int, block: str) -> Improvement | None:
        """Extract one Improvement from a raw text block."""
        # Strip end marker
        block = re.split(_IMPROVEMENT_END, block)[0]

        imp = Improvement(number=number)

        for attr, pattern in _FIELD_RE.items():
            m = pattern.search(block)
            if m:
                val = m.group(1).strip()
                if attr in ("speed_estimate", "token_estimate"):
                    try:
                        val = float(val)
                    except ValueError:
                        val = 0.0
                setattr(imp, attr, val)

        # Normalize file path (strip line numbers like ":42")
        if ":" in imp.file_path:
            imp.file_path = imp.file_path.split(":")[0].strip()
        imp.file_path = imp.file_path.replace("\\", "/")

        m = _CURRENT_CODE_RE.search(block)
        imp.current_code = m.group(1).strip() if m else ""

        m = _PROPOSED_CODE_RE.search(block)
        imp.proposed_code = m.group(1).strip() if m else ""

        m = _PROBLEM_RE.search(block)
        imp.problem = m.group(1).strip() if m else ""

        m = _REASONING_RE.search(block)
        imp.reasoning = m.group(1).strip() if m else ""

        if not imp.file_path or not imp.proposed_code:
            logger.debug("Skipping improvement #%d (missing file or proposed code)", number)
            return None

        return imp
