from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/loc_gate.py")
    parser.add_argument("root", nargs="?", default="src/poor_cli")
    parser.add_argument("--max-total", type=int, default=5000)
    parser.add_argument("--max-file", type=int, default=600)
    args = parser.parse_args()

    root = Path(args.root)
    files = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    total = 0
    too_large: list[tuple[Path, int]] = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        count = len(lines)
        total += count
        if count > args.max_file:
            too_large.append((path, count))

    if total > args.max_total:
        print(f"LOC gate failed: {total} > {args.max_total} in {root}")
        return 1
    if too_large:
        for path, count in too_large:
            print(f"LOC gate failed: {path} has {count} lines > {args.max_file}")
        return 1
    print(f"LOC gate passed: {total}/{args.max_total} lines across {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
