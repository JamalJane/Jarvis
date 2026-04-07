import pytest
from jarvis.core.screenshot import ScreenshotCapture
from jarvis.utils.compression import compress_screenshot, get_image_hash, resize_for_api


def test_screenshot_capture_initializes():
    capture = ScreenshotCapture()
    assert capture.compression_quality == 50


def test_screenshot_capture_custom_quality():
    capture = ScreenshotCapture(compression_quality=80)
    assert capture.compression_quality == 80


def test_get_image_hash_returns_string():
    from PIL import Image
    img = Image.new('RGB', (100, 100), color='red')
    hash_result = get_image_hash(img)
    assert isinstance(hash_result, str)
    assert len(hash_result) == 64


def test_resize_for_api_preserves_small():
    from PIL import Image
    img = Image.new('RGB', (100, 100), color='blue')
    resized = resize_for_api(img, 1024)
    assert resized.size == (100, 100)


def test_resize_for_api_scales_down():
    from PIL import Image
    img = Image.new('RGB', (2000, 1000), color='green')
    resized = resize_for_api(img, 1024)
    assert resized.size[0] == 1024
    assert resized.size[1] == 512
