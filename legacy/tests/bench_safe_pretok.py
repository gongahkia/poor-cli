"""Benchmark SAFE pre-tokenization: whitespace + blank lines only, no identifier changes."""
import sys, re, ast, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import tiktoken
from poor_cli.code_tokenizer import collapse_indentation, collapse_blank_lines

ROOT = Path(__file__).parent.parent
ENC = tiktoken.get_encoding("cl100k_base")
tok = lambda t: len(ENC.encode(t, disallowed_special=()))

def strip_docstrings_only(code: str) -> str:
    """Remove only docstrings (not inline comments) via AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    docstring_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)):
                ds = node.body[0]
                for ln in range(ds.lineno, ds.end_lineno + 1):
                    docstring_lines.add(ln)
    lines = code.splitlines()
    result = []
    for i, line in enumerate(lines, 1):
        if i not in docstring_lines:
            result.append(line)
    return "\n".join(result)

def strip_comment_lines_only(code: str, lang: str) -> str:
    """Remove full-line comments only (not inline). Preserves strings."""
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if lang == ".py" and stripped.startswith("#"):
            continue
        if lang == ".lua" and stripped.startswith("--"):
            continue
        if lang in (".ts", ".js") and stripped.startswith("//"):
            continue
        lines.append(line)
    return "\n".join(lines)

def safe_pretokenize(code: str, lang: str) -> str:
    """Safe: only whitespace normalization + comment-line removal. No identifier changes."""
    code = strip_comment_lines_only(code, lang)
    if lang == ".py":
        code = strip_docstrings_only(code)
    code = collapse_indentation(code)
    code = collapse_blank_lines(code)
    return code.strip()

def collect_files():
    py = sorted(ROOT.glob("poor_cli/**/*.py"))
    tests = sorted(ROOT.glob("tests/test_*.py"))[:10]
    return py + tests

def main():
    files = collect_files()
    print(f"Safe pre-tokenization benchmark: {len(files)} files\n")
    by_lang = {}
    all_results = []
    for f in files:
        try:
            code = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if len(code) < 50: continue
        lang = f.suffix
        baseline = tok(code)
        safe = safe_pretokenize(code, lang)
        safe_tokens = tok(safe)
        # verify parseability for Python
        parseable = True
        if lang == ".py":
            try:
                ast.parse(safe)
            except SyntaxError:
                parseable = False
        r = {
            "path": str(f.relative_to(ROOT)),
            "lang": lang,
            "baseline": baseline,
            "safe": safe_tokens,
            "reduction": (1 - safe_tokens / baseline) * 100 if baseline else 0,
            "parseable": parseable,
        }
        all_results.append(r)
        by_lang.setdefault(lang, []).append(r)
    # summary
    print(f"{'Lang':<6} {'N':>4} {'Baseline':>10} {'Safe':>10} {'Δ%':>7} {'Parseable':>10}")
    print("-" * 55)
    total_bl = total_sf = 0
    for lang, items in sorted(by_lang.items()):
        bl = sum(i["baseline"] for i in items)
        sf = sum(i["safe"] for i in items)
        total_bl += bl; total_sf += sf
        pct = (1 - sf / bl) * 100
        parseable = sum(1 for i in items if i["parseable"])
        print(f"{lang:<6} {len(items):>4} {bl:>10,} {sf:>10,} {pct:>6.1f}% {parseable:>4}/{len(items)}")
    print("-" * 55)
    pct = (1 - total_sf / total_bl) * 100
    parseable = sum(1 for r in all_results if r["parseable"])
    print(f"{'TOTAL':<6} {len(all_results):>4} {total_bl:>10,} {total_sf:>10,} {pct:>6.1f}% {parseable:>4}/{len(all_results)}")
    # parseability detail
    py_results = [r for r in all_results if r["lang"] == ".py"]
    unparseable = [r for r in py_results if not r["parseable"]]
    if unparseable:
        print(f"\nUnparseable Python files after safe pretok ({len(unparseable)}):")
        for r in unparseable[:10]:
            print(f"  {r['path']}")
    saved = total_bl - total_sf
    print(f"\n=== SAFE PRE-TOKENIZATION SUMMARY ===")
    print(f"Token savings: {saved:,} ({pct:.1f}%)")
    print(f"Parseability: {parseable}/{len(all_results)} ({parseable/len(all_results)*100:.1f}%)")
    print(f"Key: NO identifier changes, NO string modifications")
    print(f"Safe for: context windows (read-only files)")
    print(f"NOT safe for: edit target files (indentation changed)")

if __name__ == "__main__":
    main()
