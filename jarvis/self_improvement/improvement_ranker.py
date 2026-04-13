"""
improvement_ranker.py — scores and sorts improvements by safety × impact.

High-risk items are always sorted last so low/medium risk changes are applied
first. This minimises the blast radius if a later change fails.
"""

import logging
from jarvis.self_improvement.gemini_analyzer import Improvement

logger = logging.getLogger(__name__)

_RISK_WEIGHT = {"Low": 1.0, "Medium": 0.5, "High": 0.0}


def _score(imp: Improvement) -> float:
    """
    score = (impact * 0.5) + (safety_inv * 0.3) + (simplicity * 0.2)

    impact     = average of speed and token estimates (0-100 scale)
    safety_inv = risk weight (Low=1.0, Medium=0.5, High=0.0)
    simplicity = 1 / (1 + len(proposed_code))  — shorter patch is simpler
    """
    impact     = (imp.speed_estimate + imp.token_estimate) / 2.0
    safety_inv = _RISK_WEIGHT.get(imp.risk_level, 0.0)
    simplicity = 1.0 / (1.0 + len(imp.proposed_code))

    return (impact * 0.5) + (safety_inv * 30.0) + (simplicity * 0.2)  # safety domintaes


class ImprovementRanker:
    def rank(self, improvements: list[Improvement]) -> list[Improvement]:
        """Return a new list sorted by descending score (best first)."""
        ranked = sorted(improvements, key=_score, reverse=True)
        for i, imp in enumerate(ranked):
            logger.debug(
                "  Rank #%d — Improvement #%d (%s/%s) score=%.3f",
                i + 1, imp.number, imp.category, imp.risk_level, _score(imp),
            )
        return ranked
