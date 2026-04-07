import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserController:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None
        self.wait = None

    def start(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError:
            logger.error("Selenium not installed. Run: pip install selenium")
            return False

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")

        try:
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 10)
            logger.info("Browser started successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            return False

    def navigate(self, url: str):
        if not self.driver:
            logger.error("Browser not started")
            return False
        logger.info(f"Navigating to: {url}")
        self.driver.get(url)
        return True

    def click(self, selector: str, by: str = "css"):
        if not self.driver:
            return False
        from selenium.webdriver.common.by import By

        by_map = {
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "id": By.ID,
            "name": By.NAME,
            "class": By.CLASS_NAME,
        }
        by_type = by_map.get(by, By.CSS_SELECTOR)

        try:
            element = self.wait.until(
                lambda d: d.find_element(by_type, selector)
            )
            element.click()
            logger.info(f"Clicked: {selector}")
            return True
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return False

    def type_text(self, selector: str, text: str, by: str = "css"):
        if not self.driver:
            return False
        from selenium.webdriver.common.by import By

        by_map = {
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "id": By.ID,
            "name": By.NAME,
        }
        by_type = by_map.get(by, By.CSS_SELECTOR)

        try:
            element = self.wait.until(
                lambda d: d.find_element(by_type, selector)
            )
            element.clear()
            element.send_keys(text)
            logger.info(f"Typed '{text}' into: {selector}")
            return True
        except Exception as e:
            logger.error(f"Type failed: {e}")
            return False

    def get_dom(self) -> str:
        if not self.driver:
            return ""
        return self.driver.page_source

    def get_title(self) -> str:
        if not self.driver:
            return ""
        return self.driver.title

    def get_screenshot(self) -> Optional[bytes]:
        if not self.driver:
            return None
        try:
            return self.driver.get_screenshot_as_png()
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None

    def wait_for_element(self, selector: str, by: str = "css", timeout: int = 10):
        if not self.driver:
            return None
        from selenium.webdriver.common.by import By

        by_map = {
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "id": By.ID,
        }
        by_type = by_map.get(by, By.CSS_SELECTOR)

        try:
            from selenium.webdriver.support import expected_conditions as EC
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by_type, selector))
            )
            return element
        except Exception:
            return None

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Browser closed")

    def is_running(self) -> bool:
        return self.driver is not None
