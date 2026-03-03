"""
Image/vision helper utilities for multimodal provider payloads.
"""

import base64
import os
import re
from pathlib import Path
from typing import List, Tuple

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def encode_image(path: str) -> Tuple[str, str]:
    """Read and base64-encode an image, returning (data, mime_type)."""
    ext = Path(path).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(ext, "application/octet-stream")
    image_bytes = Path(path).read_bytes()
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return encoded, mime_type


def detect_image_paths(text: str) -> List[str]:
    """Detect absolute filesystem image paths in text and return existing files."""
    pattern = r'(?:^|\s)(/[\w./~-]+\.(?:png|jpg|jpeg|gif|webp|bmp))\b'
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    return [path for path in matches if os.path.isfile(path)]


def build_multimodal_parts_gemini(text: str, images: List[str]) -> List[dict]:
    """Build Gemini-compatible multimodal parts list."""
    parts: List[dict] = []
    for image_path in images:
        b64, mime = encode_image(image_path)
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": b64,
                }
            }
        )
    parts.append({"text": text})
    return parts


def build_multimodal_content_openai(text: str, images: List[str]) -> List[dict]:
    """Build OpenAI-compatible multimodal content array."""
    content: List[dict] = [{"type": "text", "text": text}]
    for image_path in images:
        b64, mime = encode_image(image_path)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    return content


def build_multimodal_content_anthropic(text: str, images: List[str]) -> List[dict]:
    """Build Anthropic-compatible multimodal content array."""
    content: List[dict] = []
    for image_path in images:
        b64, mime = encode_image(image_path)
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": b64,
                },
            }
        )
    content.append({"type": "text", "text": text})
    return content
