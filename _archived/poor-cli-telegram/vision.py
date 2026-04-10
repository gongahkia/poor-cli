"""Image upload handling for Telegram bot."""

import base64
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from poor_cli.exceptions import setup_logger
from poor_cli.vision import IMAGE_EXTENSIONS, encode_image

logger = setup_logger(__name__)

IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp",
}


def detect_image(document: Any) -> bool:
    """check if a Telegram document is an image by MIME type."""
    if not document:
        return False
    mime = getattr(document, "mime_type", "") or ""
    return mime in IMAGE_MIMES


def detect_photo(message: Any) -> bool:
    """check if message contains photos (compressed images)."""
    return bool(getattr(message, "photo", None))


async def download_and_encode(bot: Any, file_id: str) -> Tuple[str, str]:
    """download file from Telegram and base64 encode it."""
    tg_file = await bot.get_file(file_id)
    data = await tg_file.download_as_bytearray()
    encoded = base64.b64encode(bytes(data)).decode("utf-8")
    mime = "image/jpeg" # default, Telegram usually serves JPEG for photos
    file_path = getattr(tg_file, "file_path", "") or ""
    if file_path:
        ext = Path(file_path).suffix.lower()
        mime_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        }
        mime = mime_map.get(ext, mime)
    return encoded, mime


async def download_to_temp(bot: Any, file_id: str, suffix: str = ".jpg") -> str:
    """download file to temp path, return path string. caller must cleanup."""
    tg_file = await bot.get_file(file_id)
    data = await tg_file.download_as_bytearray()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(bytes(data))
    tmp.close()
    return tmp.name


def build_vision_prompt(images: List[Tuple[str, str]], caption: str = "") -> str:
    """construct a multimodal prompt description from images + caption."""
    text = caption or "analyze this image"
    if len(images) > 1:
        text += f" ({len(images)} images attached)"
    return text
