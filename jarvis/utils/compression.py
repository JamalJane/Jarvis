from PIL import Image
import io
import base64
import hashlib


def compress_screenshot(image: Image.Image, quality: int = 50) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode()


def capture_screen(region: tuple = None) -> Image.Image:
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=region)


def compare_screenshots(img1: Image.Image, img2: Image.Image) -> float:
    from PIL import ImageChops
    diff = ImageChops.difference(img1, img2)
    bbox = diff.getbbox()
    if bbox is None:
        return 0.0
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def get_image_hash(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def resize_for_api(image: Image.Image, max_size: int = 1024) -> Image.Image:
    width, height = image.size
    if width <= max_size and height <= max_size:
        return image
    if width > height:
        new_width = max_size
        new_height = int(height * (max_size / width))
    else:
        new_height = max_size
        new_width = int(width * (max_size / height))
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
