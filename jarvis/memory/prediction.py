import logging
from typing import Optional, Dict
from jarvis.memory.pinecone_store import PineconeStore, ActionRecord
from jarvis.config.constants import CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


class PredictionEngine:
    def __init__(self, pinecone_store: PineconeStore):
        self.store = pinecone_store
        self.confidence_scores: Dict[str, Dict] = {}

    def predict_outcome(self, action_type: str, target: str = "") -> Optional[Dict]:
        similar = self.store.query_similar(action_type, target, top_k=5)

        if len(similar) < 3:
            logger.info("Not enough historical data for prediction")
            return None

        successful = [s for s in similar if s.get("metadata", {}).get("success", False)]

        if len(successful) < 3:
            logger.info("Not enough successful outcomes for prediction")
            return None

        confidence = len(successful) / len(similar)

        if confidence >= CONFIDENCE_THRESHOLD:
            return {
                "predicted_outcome": "success",
                "confidence": confidence,
                "similar_actions": len(successful),
                "total_considered": len(similar),
            }

        return {
            "predicted_outcome": "uncertain",
            "confidence": confidence,
            "similar_actions": len(successful),
            "total_considered": len(similar),
        }

    def update_confidence(self, action_type: str, target: str, actual_success: bool):
        key = f"{action_type}_{target}"

        if key not in self.confidence_scores:
            self.confidence_scores[key] = {"successes": 0, "total": 0}

        scores = self.confidence_scores[key]
        scores["total"] += 1
        if actual_success:
            scores["successes"] += 1

        logger.info(f"Confidence for {key}: {scores['successes']}/{scores['total']}")

    def get_confidence(self, action_type: str, target: str) -> float:
        key = f"{action_type}_{target}"
        if key not in self.confidence_scores:
            return 0.0
        scores = self.confidence_scores[key]
        if scores["total"] == 0:
            return 0.0
        return scores["successes"] / scores["total"]
