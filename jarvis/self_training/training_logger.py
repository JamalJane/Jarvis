"""
Jarvis Self-Training Module
Learns from task execution outcomes, retrieves similar past tasks, auto-repairs on failure.
"""
import os
import time
import uuid
import hashlib
import logging
import json
from datetime import datetime, timezone
from typing import Optional
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

from .config import (
    SIMILARITY_THRESHOLD,
    CONFIDENCE_MISMATCH_THRESHOLD,
    EMBED_DIM,
    TRAINING_INDEX_NAME,
    AUTO_REPAIR_ENABLED,
)

EMBED_DIM = 3072

load_dotenv()

logger = logging.getLogger("jarvis.training")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GEMINI_KEYS = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
]


def _get_pinecone_index():
    if not PINECONE_API_KEY:
        logger.warning("PINECONE_API_KEY not set. Training memory disabled.")
        return None
    
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        existing = {i.name: i for i in pc.list_indexes()}
        
        if TRAINING_INDEX_NAME in existing:
            stats = pc.describe_index(TRAINING_INDEX_NAME)
            if stats.dimension != EMBED_DIM:
                logger.warning(f"Index dimension mismatch ({stats.dimension} vs {EMBED_DIM}). Deleting and recreating...")
                pc.delete_index(TRAINING_INDEX_NAME)
                existing = {}
        
        if TRAINING_INDEX_NAME not in existing:
            logger.info(f"Creating training index: {TRAINING_INDEX_NAME} (dim={EMBED_DIM})")
            pc.create_index(
                name=TRAINING_INDEX_NAME,
                dimension=EMBED_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        return pc.Index(TRAINING_INDEX_NAME)
    except Exception as e:
        logger.warning(f"Failed to connect to Pinecone: {e}")
        return None


def _get_client(key_index: int = 0):
    key = GEMINI_KEYS[key_index % len(GEMINI_KEYS)]
    if not key:
        raise ValueError(f"GEMINI_KEY_{key_index + 1} not set in .env")
    from google import genai
    return genai.Client(api_key=key)


def _embed(text: str, key_index: int = 0) -> list[float]:
    for attempt in range(len(GEMINI_KEYS)):
        try:
            client = _get_client((key_index + attempt) % len(GEMINI_KEYS))
            result = client.models.embed_content(
                model="gemini-embedding-2-preview",
                contents=text,
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.warning(f"Embed failed on key {key_index + attempt}: {e}")
    raise RuntimeError("All Gemini keys failed during embedding.")


def dom_hash(dom_snapshot: Optional[str]) -> Optional[str]:
    if not dom_snapshot:
        return None
    return hashlib.md5(dom_snapshot.encode()).hexdigest()[:12]


class TrainingLogger:
    """
    Self-training logger for Jarvis behavior learning.
    
    Usage:
        tl = TrainingLogger()
        
        # Before task
        context = tl.pre_task("fill login form")
        
        # After task
        tl.post_task(
            task_description="fill login form",
            steps_taken=["click #login", "type username"],
            outcome="success",
            confidence_before=context["confidence"],
            duration_ms=1420,
        )
    """

    def __init__(self):
        self.index = _get_pinecone_index()
        self.auto_repair_enabled = AUTO_REPAIR_ENABLED
        if self.index:
            logger.info("TrainingLogger connected to Pinecone training index.")
        else:
            logger.warning("TrainingLogger running in fallback mode (no Pinecone).")

    def pre_task(self, task_description: str) -> dict:
        """
        Query Pinecone for similar past tasks.
        Returns context with confidence, past_steps, skip_screenshot, top_match.
        """
        try:
            embedding = _embed(task_description)
            results = self.index.query(
                vector=embedding,
                top_k=3,
                include_metadata=True,
            )
            matches = results.get("matches", [])

            if not matches or matches[0]["score"] < SIMILARITY_THRESHOLD:
                return {
                    "confidence": 0.0,
                    "past_steps": [],
                    "skip_screenshot": False,
                    "top_match": None,
                }

            best = matches[0]
            confidence = best["score"]
            meta = best.get("metadata", {})

            logger.info(
                f"Memory hit: '{meta.get('task', '?')}' "
                f"score={confidence:.2f} outcome={meta.get('outcome', '?')}"
            )

            past_steps = []
            if meta.get("outcome") == "success":
                try:
                    past_steps = json.loads(meta.get("steps", "[]"))
                except Exception:
                    past_steps = []

            return {
                "confidence": confidence,
                "past_steps": past_steps,
                "skip_screenshot": confidence >= SIMILARITY_THRESHOLD and meta.get("outcome") == "success",
                "top_match": meta,
            }

        except Exception as e:
            logger.error(f"pre_task query failed: {e}")
            return {
                "confidence": 0.0,
                "past_steps": [],
                "skip_screenshot": False,
                "top_match": None,
            }

    def post_task(
        self,
        task_description: str,
        steps_taken: list[str],
        outcome: str,
        confidence_before: float = 0.0,
        duration_ms: int = 0,
        dom_snapshot: Optional[str] = None,
        gemini_key_used: int = 0,
        error_message: Optional[str] = None,
        repair_attempted: bool = False,
        repair_succeeded: bool = False,
    ):
        """
        Log task outcome to Pinecone for future retrieval.
        """
        if not self.index:
            return

        confidence_after = 1.0 if outcome == "success" else (0.5 if outcome == "partial" else 0.0)
        mismatch = abs(confidence_after - confidence_before)

        should_write = (
            outcome in ("success", "failure", "partial")
            and (
                confidence_before < SIMILARITY_THRESHOLD
                or mismatch > CONFIDENCE_MISMATCH_THRESHOLD
                or repair_attempted
                or outcome == "failure"
            )
        )

        if not should_write:
            logger.debug(f"Skipping write (routine repeat): {task_description[:60]}")
            return

        try:
            embedding = _embed(task_description, key_index=gemini_key_used)
            vector_id = str(uuid.uuid4())

            metadata = {
                "task": task_description[:500],
                "steps": json.dumps(steps_taken[:20]),
                "outcome": outcome,
                "confidence_before": round(confidence_before, 4),
                "confidence_after": round(confidence_after, 4),
                "confidence_mismatch": round(mismatch, 4),
                "duration_ms": duration_ms,
                "dom_hash": dom_hash(dom_snapshot) or "",
                "gemini_key_used": gemini_key_used,
                "repair_attempted": repair_attempted,
                "repair_succeeded": repair_succeeded,
                "error_message": (error_message or "")[:300],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.index.upsert(vectors=[{"id": vector_id, "values": embedding, "metadata": metadata}])
            logger.info(
                f"Pinecone upsert: outcome={outcome} confidence={confidence_before:.2f}->{confidence_after:.2f} "
                f"mismatch={mismatch:.2f} repair={repair_attempted}"
            )

        except Exception as e:
            logger.error(f"post_task upsert failed: {e}")

    def attempt_repair(
        self,
        task_description: str,
        failed_steps: list[str],
        error_message: str,
        key_index: int = 0,
    ) -> Optional[list[str]]:
        """
        Ask Gemini to diagnose a failed task and suggest corrected steps.
        Returns list of corrected step strings, or None if repair fails.
        """
        prompt = f"""
You are a web automation debugger for a Python + Selenium + pyautogui agent called Jarvis.

Task: {task_description}

Steps attempted:
{chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(failed_steps))}

Error: {error_message}

Diagnose the issue and respond with ONLY a JSON array of corrected step strings.
Example: ["click x=100,y=200", "type 'hello'", "press enter", "wait 1"]
No explanation, just the JSON array.
""".strip()

        for attempt in range(len(GEMINI_KEYS)):
            try:
                client = _get_client((key_index + attempt) % len(GEMINI_KEYS))
                response = client.models.generate_content(
                    model="gemini-2.0-flash-lite-001",
                    contents=[prompt]
                )
                text = response.text.strip()

                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]

                corrected = json.loads(text.strip())
                if isinstance(corrected, list):
                    logger.info(f"Self-repair succeeded: {len(corrected)} corrected steps")
                    return corrected

            except Exception as e:
                logger.warning(f"Repair attempt {attempt + 1} failed: {e}")

        logger.error("All repair attempts failed.")
        return None

    def get_stats(self) -> dict:
        """Return stats about stored training data."""
        if not self.index:
            return {"total_vectors": 0, "namespaces": {}}
        
        try:
            stats = self.index.describe_index_stats()
            return {
                "total_vectors": stats.get("total_vector_count", 0),
                "namespaces": stats.get("namespaces", {}),
            }
        except Exception as e:
            logger.error(f"Stats fetch failed: {e}")
            return {}
