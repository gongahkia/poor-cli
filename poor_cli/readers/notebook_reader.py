"""
Jupyter notebook (.ipynb) reader for poor-cli.

Parses notebook JSON and renders cells with their outputs in a
human-readable format suitable for AI consumption.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def read_notebook(file_path: str) -> str:
    """Read and render a Jupyter notebook file.

    Args:
        file_path: Path to the .ipynb file.

    Returns:
        Rendered notebook content with cell numbers, types, and outputs.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return f"error: file not found: {file_path}"
    if path.suffix.lower() != ".ipynb":
        return f"error: not a notebook file: {file_path}"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return f"error: failed to parse notebook: {exc}"

    cells = data.get("cells", [])
    metadata = data.get("metadata", {})
    kernel = metadata.get("kernelspec", {}).get("display_name", "unknown")
    lang = metadata.get("kernelspec", {}).get("language", "")
    if not lang:
        lang_info = metadata.get("language_info", {})
        lang = lang_info.get("name", "python")

    parts = [f"[Notebook: {path.name} | {len(cells)} cells | kernel: {kernel} | language: {lang}]"]

    for i, cell in enumerate(cells, 1):
        cell_type = cell.get("cell_type", "unknown")
        source = _join_source(cell.get("source", []))

        if cell_type == "markdown":
            parts.append(f"\n### Cell {i} [markdown]\n{source}")

        elif cell_type == "code":
            parts.append(f"\n### Cell {i} [code]\n```{lang}\n{source}\n```")
            outputs = cell.get("outputs", [])
            if outputs:
                output_text = _render_outputs(outputs)
                if output_text:
                    parts.append(f"**Output:**\n{output_text}")

        elif cell_type == "raw":
            parts.append(f"\n### Cell {i} [raw]\n{source}")

    return "\n".join(parts)


def _join_source(source: Any) -> str:
    """Join cell source which may be a string or list of strings."""
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def _render_outputs(outputs: List[Dict[str, Any]]) -> str:
    """Render cell outputs to text."""
    parts = []
    for output in outputs:
        output_type = output.get("output_type", "")

        if output_type == "stream":
            text = _join_source(output.get("text", ""))
            parts.append(text.rstrip())

        elif output_type in ("execute_result", "display_data"):
            data = output.get("data", {})
            if "text/plain" in data:
                parts.append(_join_source(data["text/plain"]).rstrip())
            elif "text/html" in data:
                parts.append("[HTML output]")
            if "image/png" in data:
                parts.append("[Image: base64 PNG]")
            if "image/svg+xml" in data:
                parts.append("[Image: SVG]")

        elif output_type == "error":
            ename = output.get("ename", "Error")
            evalue = output.get("evalue", "")
            parts.append(f"{ename}: {evalue}")

    return "\n".join(parts)
