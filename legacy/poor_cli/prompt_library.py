"""
Prompt library persistence for reusable user prompts.
"""

from pathlib import Path
from typing import List


class PromptLibrary:
    """Manage saved prompt snippets in a repository-scoped prompts directory."""

    def __init__(self, config_dir: Path):
        self.prompts_dir = config_dir / "prompts"

    def save(self, name: str, content: str) -> None:
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        path = self.prompts_dir / f"{name}.txt"
        path.write_text(content, encoding="utf-8")

    def load(self, name: str) -> str:
        path = self.prompts_dir / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {name}")
        return path.read_text(encoding="utf-8")

    def list_all(self) -> List[str]:
        if not self.prompts_dir.exists():
            return []
        return sorted(path.stem for path in self.prompts_dir.glob("*.txt"))

    def delete(self, name: str) -> None:
        path = self.prompts_dir / f"{name}.txt"
        if path.exists():
            path.unlink()
