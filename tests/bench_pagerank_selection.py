"""Tiny PageRank selection benchmark for poor-cli repo prompts."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from poor_cli.context import FileContext
from poor_cli.context.file_selector import FileSelector, SelectionWeights


PROMPTS = (
    ("Thread file selection through ContextAssemblyOrchestrator", "poor-cli/context_assembly.py"),
    ("Expose repo preferences for selection alpha beta gamma", "poor-cli/repo_config.py"),
    ("Use repo graph PageRank for context file candidates", "poor-cli/repo_graph.py"),
)


class _BenchGraph:
    def __init__(self, scores: dict[str, float]):
        self.scores = scores

    def pagerank_score(self, path: str) -> float:
        return self.scores.get(str(Path(path).resolve()), 0.0)

    def files_related_to(self, path: str, max_depth: int = 2):
        return []


def _candidate(root: Path, rel_path: str, mtime: float) -> FileContext:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {rel_path}\n", encoding="utf-8")
    return FileContext(
        path=str(path),
        content=path.read_text(encoding="utf-8"),
        size=path.stat().st_size,
        modified_time=mtime,
        language="python",
        source="auto",
        selection_reason="auto",
    )


def run() -> dict[str, float]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        baseline_hits = 0
        weighted_hits = 0
        for idx, (prompt, expected) in enumerate(PROMPTS):
            distractor = f"poor-cli/recent_leaf_{idx}.py"
            old_leaf = f"poor-cli/old_leaf_{idx}.py"
            candidates = [
                _candidate(root, old_leaf, 0.0),
                _candidate(root, expected, 5.0),
                _candidate(root, distractor, 10.0),
            ]
            graph = _BenchGraph(
                {
                    str((root / old_leaf).resolve()): 0.0,
                    str((root / expected).resolve()): 1.0,
                    str((root / distractor).resolve()): 0.0,
                }
            )
            baseline = FileSelector(
                repo_graph=graph,
                weights=SelectionWeights(alpha=0.6, beta=0.0, gamma=0.4),
            )
            weighted = FileSelector(
                repo_graph=graph,
                weights=SelectionWeights(alpha=0.4, beta=0.4, gamma=0.2),
            )
            baseline_top = (
                Path(baseline.rank(candidates, prompt=prompt)[0].file.path)
                .relative_to(root)
                .as_posix()
            )
            weighted_top = (
                Path(weighted.rank(candidates, prompt=prompt)[0].file.path)
                .relative_to(root)
                .as_posix()
            )
            baseline_hits += int(baseline_top == expected)
            weighted_hits += int(weighted_top == expected)
        total = len(PROMPTS)
        return {
            "baseline_accuracy": baseline_hits / total,
            "weighted_accuracy": weighted_hits / total,
        }


if __name__ == "__main__":
    result = run()
    print(f"baseline_accuracy={result['baseline_accuracy']:.3f}")
    print(f"weighted_accuracy={result['weighted_accuracy']:.3f}")
