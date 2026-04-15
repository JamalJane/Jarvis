"""
gemini_client.py — Gemini Vision API client with 4-key rotation fallback.
Rotates to the next key on any failure (rate limit, quota, timeout, error).
Logs all failures to logs/api_failures.log.
Resets key rotation order at midnight EST daily.
"""

import os
import base64
import io
import logging
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)

_failure_logger = logging.getLogger("api_failures")
_failure_logger.setLevel(logging.WARNING)
if not _failure_logger.handlers:
    fh = logging.FileHandler("logs/api_failures.log")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _failure_logger.addHandler(fh)


class AllKeysExhaustedError(Exception):
    """Raised when all Gemini API keys have failed on the same call."""
    pass


class GeminiClient:
    """
    Manages up to 5 Gemini API keys with transparent rotation on failure.
    Model: gemini-2.5-flash (vision-capable, fastest free tier).
    """

    MODEL = "gemini-2.5-flash"
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")  # Handles EST/EDT automatically

    def __init__(self):
        self.keys = [
            os.getenv("GEMINI_KEY_1", ""),
            os.getenv("GEMINI_KEY_2", ""),
            os.getenv("GEMINI_KEY_3", ""),
            os.getenv("GEMINI_KEY_4", ""),
            os.getenv("GEMINI_KEY_5", ""),
        ]
        # Remove empty keys
        self.keys = [k for k in self.keys if k]
        if not self.keys:
            raise ValueError("No Gemini API keys found in .env (GEMINI_KEY_1 … GEMINI_KEY_5)")

        self.current_key_index = 0
        self.first_used_time: dict[int, float] = {}  # key_index -> first use timestamp
        self._reset_date: str = self._today_est()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _today_est(self) -> str:
        return datetime.now(self.EASTERN).strftime("%Y-%m-%d")

    def _check_midnight_reset(self):
        """Reset rotation back to key 0 at midnight EST each day."""
        today = self._today_est()
        if today != self._reset_date:
            self.current_key_index = 0
            self.first_used_time.clear()
            self._reset_date = today
            _failure_logger.info(f"Midnight EST reset — rotating back to key 0 for {today}")

    def _rotate_key(self, failed_index: int, error: Exception):
        """Rotate to next key and log the failure."""
        timestamp = datetime.now().isoformat()
        _failure_logger.warning(
            f"Key[{failed_index + 1}] FAILED at {timestamp} | Error: {type(error).__name__}: {error}"
        )
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)

    def _get_client(self, key_index: int):
        """Build a fresh google.genai client for the given key index.
        Retries are disabled — our rotation loop handles failures instead of
        letting tenacity silently burn through RPM quota on every call.
        """
        from google import genai
        from google.genai import types
        client = genai.Client(
            api_key=self.keys[key_index],
            http_options=types.HttpOptions(timeout=30000),  # 30s timeout, no SDK retry
        )
        return client

    @staticmethod
    def _pil_to_inline(pil_image):
        """Convert a PIL Image to a google.genai Part for inline image sending."""
        from google.genai import types
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")

    # ── Public API ────────────────────────────────────────────────────────────

    def send_vision_prompt(self, screenshot_pil_image, prompt_text: str) -> str:
        """
        Send a screenshot + text prompt to Gemini Vision.
        Returns the raw text response string.
        Rotates keys transparently on any failure.
        Raises AllKeysExhaustedError if all keys fail.
        """
        self._check_midnight_reset()

        image_part = self._pil_to_inline(screenshot_pil_image)
        attempts_left = len(self.keys)
        tried_indices: set[int] = set()

        while attempts_left > 0:
            idx = self.current_key_index

            # Guard: if we've already tried this index in THIS call, all keys exhausted
            if idx in tried_indices:
                break

            tried_indices.add(idx)

            # Record first use time for this key
            if idx not in self.first_used_time:
                self.first_used_time[idx] = time.time()

            try:
                client = self._get_client(idx)
                response = client.models.generate_content(
                    model=self.MODEL,
                    contents=[image_part, prompt_text],
                )
                return response.text

            except Exception as e:
                self._rotate_key(idx, e)
                attempts_left -= 1

        # All keys exhausted
        exhausted_msg = (
            f"All {len(self.keys)} Gemini API keys failed on the same call. "
            f"Tried indices: {tried_indices}. Last error recorded in logs/api_failures.log."
        )
        _failure_logger.error(exhausted_msg)
        raise AllKeysExhaustedError(exhausted_msg)
