from __future__ import annotations

import base64
import importlib
import json
from typing import Any


def load_provider_module(module_name: str, provider_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"{provider_name} support requires optional dependency '{module_name}'. "
            "Install the provider extra before using this model."
        ) from exc


def strict_parameters(schema: dict[str, Any]) -> dict[str, Any]:
    strict = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            properties = node.get("properties", {})
            original_required = set(str(item) for item in node.get("required", []) if isinstance(item, str))
            if isinstance(properties, dict):
                node["required"] = list(properties.keys())
                for key, child in properties.items():
                    if isinstance(child, dict):
                        if key not in original_required and isinstance(child.get("type"), str):
                            child["type"] = [child["type"], "null"]
                        visit(child)
            node["additionalProperties"] = False
        elif node.get("type") == "array":
            visit(node.get("items"))

    visit(strict)
    return strict


def image_data_url(block: dict[str, Any]) -> str:
    source = block.get("source")
    if not isinstance(source, dict):
        return ""
    media_type = str(source.get("media_type", "")).strip()
    data = str(source.get("data", "")).strip()
    if not media_type or not data:
        return ""
    return f"data:{media_type};base64,{data}"


def decode_image_source(block: dict[str, Any]) -> tuple[str, bytes] | None:
    source = block.get("source")
    if not isinstance(source, dict):
        return None
    media_type = str(source.get("media_type", "")).strip()
    data = str(source.get("data", "")).strip()
    if not media_type or not data:
        return None
    return media_type, base64.b64decode(data)


def text_blocks(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text"]


def safe_json_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
