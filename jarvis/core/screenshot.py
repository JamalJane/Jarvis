import logging
from PIL import Image
from jarvis.config.constants import SCREENSHOT_COMPRESSION
from jarvis.utils.compression import compress_screenshot, capture_screen, compare_screenshots, get_image_hash, resize_for_api

logger = logging.getLogger(__name__)


class ScreenshotCapture:
    def __init__(self, compression_quality: int = None):
        self.compression_quality = compression_quality or SCREENSHOT_COMPRESSION

    def capture(self, region: tuple = None) -> tuple[Image.Image, str]:
        img = capture_screen(region)
        compressed = compress_screenshot(img, self.compression_quality)
        logger.info(f"Screenshot captured: {img.size}")
        return img, compressed

    def capture_resized(self, region: tuple = None, max_size: int = 1024) -> tuple[Image.Image, str]:
        img = capture_screen(region)
        resized = resize_for_api(img, max_size)
        compressed = compress_screenshot(resized, self.compression_quality)
        logger.info(f"Screenshot captured and resized: {img.size} -> {resized.size}")
        return resized, compressed

    def capture_and_compare(self, region: tuple = None) -> tuple[Image.Image, str, float, str, str]:
        img1, compressed1 = self.capture(region)
        img2, compressed2 = self.capture(region)
        diff_score = compare_screenshots(img1, img2)
        hash1 = get_image_hash(img1)
        hash2 = get_image_hash(img2)
        return img1, compressed1, diff_score, hash1, hash2

    def check_change(self, before: Image.Image, after: Image.Image) -> float:
        return compare_screenshots(before, after)

    def get_hash(self, image: Image.Image) -> str:
        return get_image_hash(image)
