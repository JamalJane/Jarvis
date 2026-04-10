import logging
import pyautogui

logger = logging.getLogger(__name__)


class AutomationController:
    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

    def click(self, x: int, y: int):
        pyautogui.click(x, y)
        logger.info(f"Clicked at ({x}, {y})")

    def type_text(self, text: str):
        pyautogui.typewrite(text)
        logger.info(f"Typed: {text}")

    def press(self, key: str):
        pyautogui.press(key)
        logger.info(f"Pressed: {key}")

    def scroll(self, clicks: int, x: int = None, y: int = None):
        pyautogui.scroll(clicks, x=x, y=y)
        logger.info(f"Scrolled {clicks} clicks")

    def hotkey(self, *keys):
        pyautogui.hotkey(*keys)
        logger.info(f"Hotkey: {'+'.join(keys)}")

    def move_to(self, x: int, y: int):
        pyautogui.moveTo(x, y)
        logger.info(f"Moved to ({x}, {y})")

    def double_click(self, x: int = None, y: int = None):
        pyautogui.doubleClick(x, y)
        logger.info(f"Double clicked at ({x}, {y})")

    def right_click(self, x: int = None, y: int = None):
        pyautogui.rightClick(x, y)
        logger.info(f"Right clicked at ({x}, {y})")

    def get_screenshot(self) -> bytes:
        import io
        img = pyautogui.screenshot()
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
