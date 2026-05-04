#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.repo_graph import RepoGraph
from poor_cli.repo_map import RepoMap


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(root: Path) -> list[str]:
    paths = []
    for idx in range(10):
        imports = f"from helper_{idx} import helper_{idx}\n"
        body = "\n".join(f"    total += helper_{idx}({n})" for n in range(80))
        main = root / f"feature_{idx}.py"
        helper = root / f"helper_{idx}.py"
        _write(main, f"{imports}\nclass Feature{idx}:\n    def run(self):\n        total = 0\n{body}\n        return total\n")
        _write(helper, f"def helper_{idx}(value):\n    return value + {idx}\n")
        paths.append(str(main.relative_to(root)))
    return paths


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = _fixture(root)
        graph = RepoGraph(root)
        graph.build_index()
        repo_map = RepoMap(root, graph=graph)
        savings = repo_map.estimate_savings(paths)
        read_tokens = max(1, savings["tokensIfRead"])
        reduction = savings["tokensSaved"] / read_tokens
        payload = {
            **savings,
            "reduction": round(reduction, 4),
            "threshold": 0.4,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0 if reduction >= 0.4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
