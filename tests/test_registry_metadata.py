from __future__ import annotations

import json
from pathlib import Path


EXPECTED_TARGETS = {
    "mcp.so",
    "mcp.pizza",
    "PulseMCP",
    "Smithery",
    "Anthropic Connectors Directory",
    "Official MCP Registry",
}


def test_mcp_manifest_tracks_registry_targets_and_copy() -> None:
    manifest = json.loads(Path("mcp-manifest.json").read_text(encoding="utf-8"))

    assert manifest["mcp_name"] == "io.github.gongahkia/haus"
    assert manifest["repository"] == "https://github.com/gongahkia/haus"
    assert manifest["transport"]["type"] == "stdio"
    assert manifest["listing"]["short_description"] == (
        "MCP-native HDB BTO floor-plan editor that lets agents furnish Singapore flats."
    )
    assert len(manifest["listing"]["short_description"]) <= 100

    tools = set(manifest["capabilities"]["tools"])
    assert {"design_room", "design_flat", "score_walkway", "apply_room_template"} <= tools

    targets = {entry["target"] for entry in manifest["submission_status"]}
    assert targets == EXPECTED_TARGETS


def test_official_server_json_matches_manifest_identity() -> None:
    manifest = json.loads(Path("mcp-manifest.json").read_text(encoding="utf-8"))
    server = json.loads(Path("server.json").read_text(encoding="utf-8"))

    assert server["$schema"] == "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    assert server["name"] == manifest["mcp_name"]
    assert server["title"] == manifest["title"]
    assert len(server["description"]) <= 100

    package = server["packages"][0]
    assert package["registryType"] == "pypi"
    assert package["registryBaseUrl"] == "https://pypi.org"
    assert package["identifier"] == "haus"
    assert package["runtimeHint"] == "uvx"
    assert package["transport"] == {"type": "stdio"}
    assert package["packageArguments"] == [{"type": "positional", "value": "mcp"}]


def test_registry_listing_doc_covers_all_targets() -> None:
    doc = Path("MCP_REGISTRY_LISTINGS.md").read_text(encoding="utf-8")

    for target in EXPECTED_TARGETS:
        assert target in doc

    assert "mcp-manifest.json" in doc
    assert "server.json" in doc
    assert "uvx --from git+https://github.com/gongahkia/haus haus mcp" in doc
