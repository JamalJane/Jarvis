import logging
from typing import Literal
from jarvis.memory.prediction import PredictionEngine

logger = logging.getLogger(__name__)


class ContextSelector:
    def __init__(self, prediction_engine: PredictionEngine = None):
        self.prediction_engine = prediction_engine
        self.phase = "hybrid"

    def select_context(self, task_type: Literal["web", "os", "mixed"] = "web") -> str:
        if task_type == "web":
            return self._web_context()
        elif task_type == "os":
            return self._os_context()
        else:
            return self._mixed_context()

    def _web_context(self) -> str:
        if self._can_predict():
            logger.info("Using DOM extraction (predictive mode)")
            return "dom"
        logger.info("Using hybrid context (DOM + screenshot)")
        return "hybrid"

    def _os_context(self) -> str:
        logger.info("Using screenshot context (OS tasks always need visual)")
        return "screenshot"

    def _mixed_context(self) -> str:
        logger.info("Using mixed context (DOM for web, screenshot for OS)")
        return "hybrid"

    def _can_predict(self) -> bool:
        if not self.prediction_engine:
            return False
        return self.phase == "predictive"

    def should_use_screenshot(self, action_type: str, confidence: float) -> bool:
        if confidence < 0.85:
            logger.info(f"Low confidence ({confidence}), using screenshot")
            return True
        if action_type in ["click", "type", "scroll"]:
            return False
        return True

    def set_phase(self, phase: str):
        valid_phases = ["hybrid", "predictive"]
        if phase in valid_phases:
            self.phase = phase
            logger.info(f"Context selector phase set to: {phase}")
        else:
            logger.warning(f"Invalid phase: {phase}")
