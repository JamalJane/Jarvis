"""
Jarvis Auto-Trainer Daemon

Autonomous training system that improves Jarvis's task execution confidence.
Pulls tasks from 3 sources: tasks.txt, past real tasks from Pinecone, and generated variations.
Trains until all tasks reach 95% confidence or user stops.

Usage:
    python -m jarvis.self_training.auto_trainer
    python jarvis/self_training/auto_trainer.py

Stop: Ctrl+C (saves state cleanly)
"""

import os
import sys
import time
import json
import random
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from jarvis.self_training.training_logger import TrainingLogger, _embed
from jarvis.self_training.config import SIMILARITY_THRESHOLD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("jarvis_training.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("jarvis.auto_trainer")

TASKS_FILE = Path("tasks.txt")
STATE_FILE = Path("trainer_state.json")
IDLE_SLEEP_SEC = 5
VARIATION_BATCH = 3
MAX_RETRIES = 2
CONFIDENCE_TARGET = 0.95
RATE_LIMIT_WAIT_SEC = 60
GEMINI_KEYS = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
]


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "tasks_file_index": 0,
        "total_trained": 0,
        "total_success": 0,
        "total_failure": 0,
        "total_repaired": 0,
        "session_start": datetime.now(timezone.utc).isoformat(),
        "last_task": None,
        "confidence_scores": {},
        "training_complete": False,
    }


def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def load_tasks_file() -> list[str]:
    if not TASKS_FILE.exists():
        default_tasks = [
            "search google for python tutorials",
            "search google for latest AI news",
            "search google for weather in New York",
            "open youtube and search for lo-fi music",
            "go to reddit.com and read the top post",
            "open wikipedia and search for artificial intelligence",
            "go to github.com and search for open source projects",
            "open hacker news and find the top story",
            "go to bbc.com and read a headline",
            "scrape the top 5 headlines from bbc.com",
            "get the current bitcoin price from coinmarketcap",
            "find the top trending topics on twitter",
            "go to google.com and search for open source projects",
            "open duckduckgo and search for privacy tools",
            "search github for trending python repositories",
        ]
        TASKS_FILE.write_text(
            "# Jarvis training tasks — one per line\n"
            "# Lines starting with # are ignored\n\n"
            + "\n".join(default_tasks)
        )
        logger.info(f"Created tasks.txt with {len(default_tasks)} default tasks")
        return default_tasks
    
    lines = TASKS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def fetch_past_tasks_from_pinecone(tl: TrainingLogger, limit: int = 30) -> list[str]:
    try:
        dummy_embed = _embed("automation task web browser")
        results = tl.index.query(
            vector=dummy_embed,
            top_k=limit,
            include_metadata=True,
        )
        tasks = []
        seen = set()
        for match in results.get("matches", []):
            task = match.get("metadata", {}).get("task")
            if task and task not in seen:
                tasks.append(task)
                seen.add(task)
        logger.info(f"Fetched {len(tasks)} past tasks from Pinecone")
        return tasks
    except Exception as e:
        logger.error(f"Failed to fetch past tasks: {e}")
        return []


def generate_variations(task: str, key_index: int = 0, n: int = VARIATION_BATCH, max_attempts: int = 3) -> list[str]:
    from google import genai
    
    prompt = f"""
Generate {n} natural-language variations of this web automation task.
Keep them realistic and slightly different (different site, search term, or phrasing).

Original task: {task}

Respond ONLY with a JSON array of {n} strings. No explanation.
Example: ["variation one", "variation two", "variation three"]
""".strip()

    for attempt in range(max_attempts):
        for ki in range(len(GEMINI_KEYS)):
            try:
                key = GEMINI_KEYS[(key_index + ki) % len(GEMINI_KEYS)]
                if not key:
                    continue
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model="gemini-2.0-flash-lite-001",
                    contents=[prompt]
                )
                text = response.text.strip()

                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]

                variations = json.loads(text.strip())
                if isinstance(variations, list):
                    return [v for v in variations if isinstance(v, str)][:n]
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate limit" in error_str or "resource_exhausted" in error_str:
                    retry_delay = float(attempt + 1) * 10
                    logger.warning(f"Rate limited on key {ki}, waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    continue
                logger.warning(f"Variation generation failed (key {ki}): {e}")
        
        if attempt < max_attempts - 1:
            wait_time = (attempt + 1) * 30
            logger.warning(f"All keys rate limited, waiting {wait_time}s...")
            time.sleep(wait_time)
    
    return []


class JarvisExecutor:
    """Wraps TaskManager for use in auto-trainer."""
    
    def __init__(self):
        from jarvis.config.api_manager import APIManager
        from jarvis.core.browser import BrowserController
        from jarvis.core.automation import AutomationController
        
        self.api_manager = APIManager()
        self.browser = BrowserController()
        self.automation = AutomationController()
        
        self.task_history = []
        logger.info("JarvisExecutor initialized")
    
    def execute(self, task_description: str, past_steps: list = None, skip_screenshot: bool = False) -> dict:
        """
        Execute a task using Jarvis's real TaskManager.
        Returns dict with steps_taken, outcome, error_message, gemini_key_used.
        """
        from jarvis.core.task_manager import TaskManager, TaskResult
        
        training_logger = TrainingLogger()
        task_manager = TaskManager(
            api_manager=self.api_manager,
            browser=self.browser,
            automation=self.automation,
            training_logger=training_logger,
        )
        
        try:
            result = task_manager.execute_task(task_description)
            
            return {
                "steps_taken": [h['action'] for h in task_manager.task_history],
                "outcome": "success" if result.success else "failure",
                "error_message": result.error,
                "gemini_key_used": 0,
            }
        except Exception as e:
            logger.error(f"Task execution error: {e}")
            return {
                "steps_taken": [],
                "outcome": "failure",
                "error_message": str(e),
                "gemini_key_used": 0,
            }


def run_one_task(
    task: str,
    tl: TrainingLogger,
    state: dict,
    executor: JarvisExecutor,
    key_index: int = 0,
) -> dict:
    """Run a single task through pre→execute→repair→post pipeline."""
    logger.info(f"Training task: {task[:80]}")

    start = time.time()

    context = tl.pre_task(task)
    logger.info(f"  Confidence: {context['confidence']:.2f} | Skip: {context['skip_screenshot']}")

    result = {"steps_taken": [], "outcome": "failure", "error_message": None, "gemini_key_used": key_index}
    repair_attempted = False
    repair_succeeded = False

    for attempt in range(MAX_RETRIES):
        try:
            result = executor.execute(
                task_description=task,
                past_steps=context["past_steps"],
                skip_screenshot=context["skip_screenshot"],
            )
            if result["outcome"] != "failure":
                break
        except Exception as e:
            result["error_message"] = str(e)
            result["outcome"] = "failure"
            logger.warning(f"  Attempt {attempt + 1} raised: {e}")

    if result["outcome"] == "failure" and result.get("steps_taken"):
        repair_attempted = True
        logger.info("  Attempting self-repair...")
        corrected = tl.attempt_repair(
            task_description=task,
            failed_steps=result["steps_taken"],
            error_message=result.get("error_message", "unknown"),
            key_index=key_index,
        )
        if corrected:
            try:
                result = executor.execute(
                    task_description=task,
                    past_steps=corrected,
                    skip_screenshot=False,
                )
                repair_succeeded = result["outcome"] == "success"
                if repair_succeeded:
                    logger.info("  Self-repair succeeded!")
            except Exception as e:
                result["error_message"] = str(e)

    duration_ms = int((time.time() - start) * 1000)

    tl.post_task(
        task_description=task,
        steps_taken=result.get("steps_taken", []),
        outcome=result.get("outcome", "failure"),
        confidence_before=context["confidence"],
        duration_ms=duration_ms,
        gemini_key_used=result.get("gemini_key_used", key_index),
        error_message=result.get("error_message"),
        repair_attempted=repair_attempted,
        repair_succeeded=repair_succeeded,
    )

    state["total_trained"] += 1
    state["last_task"] = task
    
    confidence = context["confidence"]
    if result["outcome"] == "success":
        state["total_success"] += 1
        confidence = max(confidence, 0.95)
    elif result["outcome"] == "failure":
        state["total_failure"] += 1
        confidence = min(confidence, 0.3)
    
    state["confidence_scores"][task] = confidence
    if repair_succeeded:
        state["total_repaired"] += 1

    outcome_symbol = "✓" if result["outcome"] == "success" else ("~" if result["outcome"] == "partial" else "✗")
    logger.info(
        f"  {outcome_symbol} {result['outcome'].upper()} | "
        f"{duration_ms}ms | conf={confidence:.2f} | "
        f"total={state['total_trained']} success={state['total_success']} fail={state['total_failure']}"
    )

    return result


def check_training_complete(state: dict, all_tasks: list[str]) -> bool:
    """Check if all tasks have reached target confidence."""
    if not state["confidence_scores"]:
        return False
    
    scores = state["confidence_scores"]
    task_scores = []
    
    for task in all_tasks:
        score = scores.get(task, 0.0)
        task_scores.append((task, score))
        if score < CONFIDENCE_TARGET:
            return False
    
    avg_confidence = sum(s[1] for s in task_scores) / len(task_scores) if task_scores else 0
    
    logger.info("=" * 60)
    logger.info("  TRAINING COMPLETE!")
    logger.info(f"  Average confidence: {avg_confidence:.2%}")
    logger.info(f"  Tasks trained: {len(task_scores)}")
    for task, score in sorted(task_scores, key=lambda x: x[1]):
        logger.info(f"    {score:.2%} | {task[:60]}")
    logger.info("=" * 60)
    
    state["training_complete"] = True
    return True


def print_stats(tl: TrainingLogger, state: dict, all_tasks: list[str]):
    scores = state.get("confidence_scores", {})
    
    trained = len(scores)
    ready = sum(1 for s in scores.values() if s >= CONFIDENCE_TARGET)
    avg = sum(scores.values()) / len(scores) if scores else 0
    
    logger.info("─" * 60)
    logger.info("  TRAINING PROGRESS")
    logger.info(f"  Tasks: {trained}/{len(all_tasks)} trained | {ready} at {CONFIDENCE_TARGET:.0%}+ confidence")
    logger.info(f"  Average confidence: {avg:.2%}")
    logger.info(f"  Total runs: {state['total_trained']} | Success: {state['total_success']} | Fail: {state['total_failure']}")
    logger.info(f"  Self-repaired: {state['total_repaired']}")
    
    if scores:
        logger.info("  Task confidence scores:")
        for task, score in sorted(scores.items(), key=lambda x: x[1])[:5]:
            status = "✓" if score >= CONFIDENCE_TARGET else "○"
            logger.info(f"    {status} {score:.0%} | {task[:50]}")
    logger.info("─" * 60)


class AutoTrainer:
    def __init__(self):
        self.tl = TrainingLogger()
        self.state = load_state()
        self.executor = JarvisExecutor()
        self._stop = threading.Event()

        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)

        logger.info("=" * 60)
        logger.info("  JARVIS AUTO-TRAINER STARTED")
        logger.info(f"  Confidence target: {CONFIDENCE_TARGET:.0%}")
        logger.info(f"  Sources: tasks.txt + past tasks + variations")
        logger.info("=" * 60)

    def _handle_stop(self, *_):
        logger.info("Shutdown signal received — saving state and stopping...")
        self._stop.set()

    def _build_task_queue(self) -> list[str]:
        queue = []

        file_tasks = load_tasks_file()
        queue.extend(file_tasks)
        logger.info(f"Loaded {len(file_tasks)} tasks from tasks.txt")

        past_tasks = fetch_past_tasks_from_pinecone(self.tl, limit=30)
        for task in past_tasks:
            if task not in queue:
                queue.append(task)
        logger.info(f"Loaded {len(past_tasks)} past tasks from Pinecone")

        seed_tasks = random.sample(queue, min(len(queue), 10)) if queue else []
        all_variations = []
        for seed in seed_tasks:
            if self._stop.is_set():
                break
            variations = generate_variations(seed, key_index=0, n=VARIATION_BATCH)
            all_variations.extend(variations)
            time.sleep(0.3)

        queue.extend(all_variations)
        logger.info(f"Generated {len(all_variations)} variations")
        logger.info(f"Total queue: {len(queue)} tasks")

        random.shuffle(queue)
        return queue

    def run(self):
        key_index = 0

        while not self._stop.is_set():
            logger.info("Building training queue...")
            all_tasks = load_tasks_file()
            
            past_tasks = fetch_past_tasks_from_pinecone(self.tl, limit=30)
            for task in past_tasks:
                if task not in all_tasks:
                    all_tasks.append(task)

            if check_training_complete(self.state, all_tasks):
                save_state(self.state)
                print_stats(self.tl, self.state, all_tasks)
                logger.info("Training complete! All tasks reached target confidence.")
                break

            queue = self._build_task_queue()

            if not queue:
                logger.warning("Task queue empty — sleeping 60s before retry.")
                time.sleep(60)
                continue

            for i, task in enumerate(queue):
                if self._stop.is_set():
                    break

                if check_training_complete(self.state, all_tasks):
                    break

                try:
                    run_one_task(task, self.tl, self.state, self.executor, key_index=key_index)
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "rate limit" in error_str or "resource_exhausted" in error_str:
                        logger.warning(f"Rate limited! Waiting {RATE_LIMIT_WAIT_SEC}s before retry...")
                        time.sleep(RATE_LIMIT_WAIT_SEC)
                        continue
                    else:
                        logger.error(f"Task error: {e}")
                
                save_state(self.state)

                key_index = (key_index + 1) % len(GEMINI_KEYS)

                if self.state["total_trained"] % 5 == 0:
                    print_stats(self.tl, self.state, all_tasks)

                time.sleep(IDLE_SLEEP_SEC)

            logger.info("Queue cycle complete — checking progress...")

        save_state(self.state)
        print_stats(self.tl, self.state, all_tasks)
        logger.info("Auto-trainer stopped.")


if __name__ == "__main__":
    import threading
    
    trainer = AutoTrainer()
    trainer.run()
