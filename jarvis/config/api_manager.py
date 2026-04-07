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
        if self.current_key_index < len(API_KEYS):
            key_name = API_KEYS[self.current_key_index]
            return self.keys.get(key_name)
        return None

    def call_api(self, prompt: str, image_base64: str = None) -> str:
        self._check_daily_reset()

        for attempt in range(len(API_KEYS)):
            key = self.get_current_key()
            if not key:
                logger.warning(f"No key at index {self.current_key_index}, trying next")
                self.current_key_index += 1
                continue

            try:
                import google.generativeai as genai
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-2.0-flash')

                content = [prompt]
                if image_base64:
                    from PIL import Image
                    import io
                    import base64

                    img_data = base64.b64decode(image_base64)
                    img = Image.open(io.BytesIO(img_data))
                    content.append(img)

                response = model.generate_content(content)
                self.request_counts[API_KEYS[self.current_key_index]] += 1
                logger.info(f"API call succeeded with {API_KEYS[self.current_key_index]}")
                return response.text

            except Exception as e:
                logger.warning(f"API call failed with {API_KEYS[self.current_key_index]}: {e}")
                self.current_key_index += 1
                continue

        raise RuntimeError("All API keys exhausted")

    def _check_daily_reset(self):
        now = datetime.now()
        if now - self.last_reset > timedelta(days=1):
            self.request_counts = {k: 0 for k in API_KEYS}
            self.current_key_index = 0
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
                "total": DAILY_REQUEST_LIMIT
            }
        return {
            "current_key": API_KEYS[self.current_key_index] if self.current_key_index < len(API_KEYS) else "none",
            "status": status,
        }
