from pathlib import Path

from poor_cli.repo_config import _repo_configs, get_repo_config
from poor_cli.state_portability import export_state, inspect_repo_state, remove_repo_state


def test_repo_config_uses_workspace_root_for_nested_cwd(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    nested = root / "packages" / "app"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    _repo_configs.clear()

    cfg = get_repo_config(repo_path=nested, enable_legacy_history_migration=False)

    assert cfg.repo_path == root
    assert (root / ".poor-cli").is_dir()
    assert not (nested / ".poor-cli").exists()
    assert (root / ".poor-cli" / "STATE.md").is_file()


def test_repo_state_remove_reports_and_deletes_workspace_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    _repo_configs.clear()
    get_repo_config(repo_path=root, enable_legacy_history_migration=False)

    before = inspect_repo_state(repo_root=root)
    removed = remove_repo_state(repo_root=root)
    after = inspect_repo_state(repo_root=root)

    assert before.exists is True
    assert removed.files >= 1
    assert after.exists is False


def test_state_export_uses_workspace_root_from_nested_cwd(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    nested = root / "packages" / "app"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    state_dir = root / ".poor-cli" / "context"
    state_dir.mkdir(parents=True)
    (state_dir / "MAP.md").write_text("# map\n", encoding="utf-8")

    archive = tmp_path / "state.zip"
    exported = export_state(archive, repo_root=nested)

    assert "repo/context/MAP.md" in exported.files
