import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

from .constants import API_KEYS, DAILY_REQUEST_LIMIT

logger = logging.getLogger(__name__)


class APIManager:
    def __init__(self):
        load_dotenv()
        self.keys = self._load_keys()
        self.current_key_index = 0
        self.request_counts = {k: 0 for k in API_KEYS}
        self.failed_keys = set()
        self.last_reset = datetime.now()

    def _load_keys(self) -> dict:
        keys = {}
        for key_name in API_KEYS:
            value = os.getenv(key_name)
            if value:
                keys[key_name] = value
                logger.info(f"Loaded {key_name}")
        logger.info(f"Total keys loaded: {len(keys)}")
        return keys

    def get_current_key(self) -> Optional[str]:
        while self.current_key_index < len(API_KEYS):
            key_name = API_KEYS[self.current_key_index]
            if key_name in self.failed_keys:
                logger.warning(f"Skipping failed key: {key_name}")
                self.current_key_index += 1
                continue
            return self.keys.get(key_name)
        return None
    
    def mark_key_failed(self, key_name: str):
        if key_name in API_KEYS:
            self.failed_keys.add(key_name)
            logger.warning(f"Key marked as failed: {key_name}")

    def validate_keys(self):
        import concurrent.futures
        from google import genai

        def test_key(key_name):
            key = self.keys.get(key_name)
            if not key:
                self.failed_keys.add(key_name)
                return False
            try:
                client = genai.Client(api_key=key)
                client.models.generate_content(model="gemini-2.5-flash", contents=["hi"])
                return True
            except Exception as e:
                logger.warning(f"Key {key_name} failed validation: {e}")
                self.failed_keys.add(key_name)
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(API_KEYS)) as executor:
            futures = [executor.submit(test_key, k) for k in API_KEYS]
            concurrent.futures.wait(futures)

        # Ensure current_key_index skips failed keys
        while self.current_key_index < len(API_KEYS):
            if API_KEYS[self.current_key_index] not in self.failed_keys:
                break
            self.current_key_index += 1

    def call_api(self, prompt: str, image_base64: str = None) -> str:
        self._check_daily_reset()

        for attempt in range(len(API_KEYS)):
            key = self.get_current_key()
            if not key:
                logger.warning(f"No key at index {self.current_key_index}, trying next")
                self.current_key_index += 1
                continue

            try:
                from google import genai
                client = genai.Client(api_key=key)

                content = [prompt]
                if image_base64:
                    from PIL import Image
                    import io
                    import base64

                    img_data = base64.b64decode(image_base64)
                    img = Image.open(io.BytesIO(img_data))
                    content.append(img)

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=content
                )
                self.request_counts[API_KEYS[self.current_key_index]] += 1
                logger.info(f"API call succeeded with {API_KEYS[self.current_key_index]}")
                return response.text

            except Exception as e:
                error_str = str(e).lower()
                key_name = API_KEYS[self.current_key_index]
                
                if any(x in error_str for x in ["429", "rate limit", "quota", "exhausted", "resource exhausted"]):
                    logger.warning(f"Rate limit on {key_name}, marking as failed")
                    self.mark_key_failed(key_name)
                elif any(x in error_str for x in ["403", "forbidden", "invalid", "permission"]):
                    logger.warning(f"Invalid credentials on {key_name}, marking as failed")
                    self.mark_key_failed(key_name)
                else:
                    logger.warning(f"API call failed with {key_name}: {e}")
                
                self.current_key_index += 1
                continue

        raise RuntimeError("All API keys exhausted")

    def _check_daily_reset(self):
        now = datetime.now()
        if now - self.last_reset > timedelta(days=1):
            self.request_counts = {k: 0 for k in API_KEYS}
            self.current_key_index = 0
            self.failed_keys.clear()
            self.last_reset = now
            logger.info("API request counts reset")

    def get_status(self) -> dict:
        status = {}
        for key_name, count in self.request_counts.items():
            display_name = key_name.replace("GEMINI_KEY_", "Gemini ")
            remaining = DAILY_REQUEST_LIMIT - count
            status[display_name] = {
                "used": count,
                "remaining": remaining,
                "total": DAILY_REQUEST_LIMIT,
                "failed": key_name in self.failed_keys
            }
        return {
            "current_key": API_KEYS[self.current_key_index] if self.current_key_index < len(API_KEYS) else "none",
            "status": status,
            "failed_keys": list(self.failed_keys)
        }
