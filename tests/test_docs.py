from __future__ import annotations

from pathlib import Path


def test_docs_pages_workflow_builds_mkdocs_site() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "docs-pages.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "mkdocs build --strict" in text
    assert "actions/upload-pages-artifact@v3" in text
    assert "actions/deploy-pages@v4" in text
    assert "path: site" in text
