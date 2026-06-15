from __future__ import annotations

from pathlib import Path


def test_docs_pages_workflow_builds_mkdocs_site() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "docs-pages.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "mkdocs build --strict" in text
    assert "actions/upload-pages-artifact@v3" in text
    assert "actions/deploy-pages@v4" in text
    assert "path: site" in text


def test_docs_cover_provider_native_artifacts_and_migration() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    architecture = (root / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    migration = (root / "docs" / "migration.md").read_text(encoding="utf-8")
    security = (root / "docs" / "security.md").read_text(encoding="utf-8")
    release = (root / "docs" / "release-checklist.md").read_text(encoding="utf-8")
    graph = (root / "docs" / "graph.md").read_text(encoding="utf-8")
    shell_adr = (root / "docs" / "adr-shell-sandbox.md").read_text(encoding="utf-8")
    mkdocs = (root / "mkdocs.yml").read_text(encoding="utf-8")

    assert "provider add openai" in readme
    assert "runs/<run_id>/artifacts" in readme
    assert "ProviderBackedAgentRunner" in architecture
    assert "Existing CLI flows remain supported" in migration
    assert "6500 lines" in migration
    assert "command substitution" in security
    assert "python bench/packaging_gate.py" in release
    assert "Language Matrix" in graph
    assert "Use Python `shlex` only" in shell_adr
    assert "Security: security.md" in mkdocs
