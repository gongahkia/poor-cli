import base64

from poor_cli.vision import (
    build_multimodal_content_anthropic,
    build_multimodal_content_openai,
    build_multimodal_parts_gemini,
    detect_image_paths,
    encode_image,
)


def test_encode_image_and_builders(tmp_path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    encoded, mime = encode_image(str(image_path))
    assert mime == "image/png"
    assert base64.b64decode(encoded) == b"\x89PNG\r\n\x1a\nfake"

    gemini_parts = build_multimodal_parts_gemini("describe", [str(image_path)])
    assert gemini_parts[-1]["text"] == "describe"
    assert gemini_parts[0]["inline_data"]["mime_type"] == "image/png"

    openai_content = build_multimodal_content_openai("describe", [str(image_path)])
    assert openai_content[0]["type"] == "text"
    assert openai_content[1]["type"] == "image_url"

    anthropic_content = build_multimodal_content_anthropic("describe", [str(image_path)])
    assert anthropic_content[0]["type"] == "image"
    assert anthropic_content[-1]["type"] == "text"


def test_detect_image_paths_filters_existing_files(tmp_path):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"jpeg")
    text = f"check {image_path} and /does/not/exist.png"
    found = detect_image_paths(text)
    assert str(image_path) in found
    assert "/does/not/exist.png" not in found
