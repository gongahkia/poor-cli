from __future__ import annotations

from poor_cli.server import registry


def test_static_index_matches_current_handler_ast_scan() -> None:
    static = registry._load_static_indexes()
    assert static is not None
    static_rpc, static_attr = static

    ast_rpc, ast_attr = registry._scan_indexes_from_ast()
    assert static_rpc == ast_rpc
    assert static_attr == ast_attr
