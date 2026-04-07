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
        if self.driver:
            try:
                self.driver.current_url
                return True
            except:
                self.driver = None

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
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

    def _ensure_running(self) -> bool:
        if not self.driver:
            return self.start()
        try:
            self.driver.current_url
            return True
        except:
            logger.warning("Browser crashed, restarting...")
            self.driver = None
            return self.start()

    def navigate(self, url: str):
        if not self._ensure_running():
            logger.error("Browser not running")
            return False
        logger.info(f"Navigating to: {url}")
        try:
            self.driver.get(url)
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    def click(self, selector: str, by: str = "css"):
        if not self._ensure_running():
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
        if not self._ensure_running():
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
        if not self._ensure_running():
            return ""
        try:
            return self.driver.page_source
        except:
            return ""

    def get_title(self) -> str:
        if not self._ensure_running():
            return ""
        try:
            return self.driver.title
        except:
            return ""

    def get_screenshot(self) -> Optional[bytes]:
        if not self._ensure_running():
            return None
        try:
            return self.driver.get_screenshot_as_png()
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return None

    def wait_for_element(self, selector: str, by: str = "css", timeout: int = 10):
        if not self._ensure_running():
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
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            logger.info("Browser closed")

    def is_running(self) -> bool:
        if not self.driver:
            return False
        try:
            self.driver.current_url
            return True
        except:
            self.driver = None
            return False
