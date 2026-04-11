"""Full benchmark: baseline vs pre-tokenization vs AST-compact vs combined."""
import sys, json, statistics, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import tiktoken
from poor_cli.code_tokenizer import pretokenize, ast_compact_python, pretokenize_ast

ROOT = Path(__file__).parent.parent
ENC = tiktoken.get_encoding("cl100k_base")

def tok(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))

def collect_files():
    py = sorted(ROOT.glob("poor_cli/**/*.py"))
    lua = sorted(ROOT.glob("nvim-poor-cli/**/*.lua"))
    ts = sorted(ROOT.glob("_archived/**/*.ts"))
    tests = sorted(ROOT.glob("tests/test_*.py"))[:10]
    return py + lua + ts + tests

def roundtrip_check_python(original: str, transformed: str) -> dict:
    """Check if key identifiers and structure are preserved."""
    import re
    orig_defs = set(re.findall(r'\bdef (\w+)', original))
    trans_defs = set(re.findall(r'\bdef (\w+)', transformed))
    orig_classes = set(re.findall(r'\bclass (\w+)', original))
    trans_classes = set(re.findall(r'\bclass (\w+)', transformed))
    # check identifier preservation (names should still be findable)
    missing_defs = orig_defs - trans_defs
    missing_classes = orig_classes - trans_classes
    return {
        "defs_preserved": len(orig_defs - missing_defs) / max(len(orig_defs), 1),
        "classes_preserved": len(orig_classes - missing_classes) / max(len(orig_classes), 1),
        "missing_defs": list(missing_defs)[:5],
        "missing_classes": list(missing_classes)[:5],
    }

def benchmark_file(path: Path) -> dict | None:
    try:
        code = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if len(code) < 50: return None
    lang = path.suffix
    baseline_tokens = tok(code)
    # approach A: pre-tokenization
    try:
        pretok = pretokenize(code, lang)
        pretok_tokens = tok(pretok)
    except Exception as e:
        pretok = code
        pretok_tokens = baseline_tokens
    # approach B: AST-compact (Python only)
    if lang == ".py":
        try:
            compact = ast_compact_python(code)
            if compact:
                compact_tokens = tok(compact)
            else:
                compact = None
                compact_tokens = None
        except Exception:
            compact = None
            compact_tokens = None
    else:
        compact = None
        compact_tokens = None
    # approach A+B combined
    if lang == ".py":
        try:
            combined = pretokenize_ast(code, lang)
            combined_tokens = tok(combined)
        except Exception:
            combined = None
            combined_tokens = None
    else:
        combined = pretokenize(code, lang) # just pretok for non-Python
        combined_tokens = tok(combined)
    # roundtrip check for Python
    rt = None
    if lang == ".py" and compact:
        rt = roundtrip_check_python(code, compact)
    return {
        "path": str(path.relative_to(ROOT)),
        "lang": lang,
        "baseline": baseline_tokens,
        "pretok": pretok_tokens,
        "pretok_reduction": (1 - pretok_tokens / baseline_tokens) * 100,
        "ast_compact": compact_tokens,
        "ast_reduction": (1 - compact_tokens / baseline_tokens) * 100 if compact_tokens else None,
        "combined": combined_tokens,
        "combined_reduction": (1 - combined_tokens / baseline_tokens) * 100 if combined_tokens else None,
        "roundtrip": rt,
        "chars_original": len(code),
        "chars_pretok": len(pretok),
        "chars_compact": len(compact) if compact else None,
    }

def main():
    files = collect_files()
    print(f"Benchmarking {len(files)} files with cl100k_base encoding\n")
    results = []
    for f in files:
        r = benchmark_file(f)
        if r: results.append(r)
    # aggregate by language
    by_lang = {}
    for r in results:
        by_lang.setdefault(r["lang"], []).append(r)
    print(f"{'Lang':<6} {'N':>4} {'Baseline':>10} {'PreTok':>10} {'ΔPT%':>7} {'AST':>10} {'ΔAST%':>7} {'Combined':>10} {'ΔCmb%':>7}")
    print("-" * 85)
    totals = {"baseline": 0, "pretok": 0, "ast": 0, "combined": 0}
    for lang, items in sorted(by_lang.items()):
        bl = sum(i["baseline"] for i in items)
        pt = sum(i["pretok"] for i in items)
        ac = sum(i["ast_compact"] for i in items if i["ast_compact"])
        ac_bl = sum(i["baseline"] for i in items if i["ast_compact"])
        cb = sum(i["combined"] for i in items if i["combined"])
        cb_bl = sum(i["baseline"] for i in items if i["combined"])
        totals["baseline"] += bl
        totals["pretok"] += pt
        totals["ast"] += ac
        totals["combined"] += cb
        pt_pct = (1 - pt / bl) * 100 if bl else 0
        ac_pct = (1 - ac / ac_bl) * 100 if ac_bl else 0
        cb_pct = (1 - cb / cb_bl) * 100 if cb_bl else 0
        ac_str = f"{ac:>10,}" if ac else f"{'N/A':>10}"
        ac_pct_str = f"{ac_pct:>6.1f}%" if ac else f"{'N/A':>7}"
        print(f"{lang:<6} {len(items):>4} {bl:>10,} {pt:>10,} {pt_pct:>6.1f}% {ac_str} {ac_pct_str} {cb:>10,} {cb_pct:>6.1f}%")
    print("-" * 85)
    bl = totals["baseline"]
    pt = totals["pretok"]
    ac = totals["ast"]
    cb = totals["combined"]
    print(f"{'TOTAL':<6} {len(results):>4} {bl:>10,} {pt:>10,} {(1-pt/bl)*100:>6.1f}% {ac:>10,} {'':>7} {cb:>10,} {(1-cb/bl)*100:>6.1f}%")
    # roundtrip accuracy
    py_with_rt = [r for r in results if r["roundtrip"]]
    if py_with_rt:
        avg_def = statistics.mean(r["roundtrip"]["defs_preserved"] for r in py_with_rt)
        avg_cls = statistics.mean(r["roundtrip"]["classes_preserved"] for r in py_with_rt)
        print(f"\nRoundtrip accuracy (Python AST-compact):")
        print(f"  Function defs preserved: {avg_def*100:.1f}%")
        print(f"  Class defs preserved:    {avg_cls*100:.1f}%")
    # per-file detail for top reductions
    print(f"\nTop 15 files by AST-compact reduction:")
    ast_results = sorted([r for r in results if r["ast_reduction"]], key=lambda r: r["ast_reduction"], reverse=True)
    for r in ast_results[:15]:
        print(f"  {r['path']:<55} {r['baseline']:>6} → {r['ast_compact']:>6} ({r['ast_reduction']:>5.1f}%)")
    print(f"\nTop 15 files by pre-tokenization reduction:")
    pt_results = sorted(results, key=lambda r: r["pretok_reduction"], reverse=True)
    for r in pt_results[:15]:
        print(f"  {r['path']:<55} {r['baseline']:>6} → {r['pretok']:>6} ({r['pretok_reduction']:>5.1f}%)")
    # files where AST-compact INCREASED tokens
    worse = [r for r in results if r["ast_reduction"] and r["ast_reduction"] < 0]
    if worse:
        print(f"\nFiles where AST-compact INCREASED tokens ({len(worse)}):")
        for r in sorted(worse, key=lambda r: r["ast_reduction"])[:10]:
            print(f"  {r['path']:<55} {r['baseline']:>6} → {r['ast_compact']:>6} ({r['ast_reduction']:>+5.1f}%)")
    # summary stats
    print("\n=== SUMMARY ===")
    print(f"Total files analyzed: {len(results)}")
    print(f"Baseline tokens:     {totals['baseline']:>10,}")
    pt_save = totals['baseline'] - totals['pretok']
    print(f"Pre-tokenization:    {totals['pretok']:>10,}  (saves {pt_save:,} tokens, {pt_save/totals['baseline']*100:.1f}%)")
    if totals['ast']:
        ast_save = totals['baseline'] - totals['ast']
        print(f"AST-compact:         {totals['ast']:>10,}  (saves ~{ast_save:,} tokens on Python files)")
    cb_save = totals['baseline'] - totals['combined']
    print(f"Combined (A+B):      {totals['combined']:>10,}  (saves {cb_save:,} tokens, {cb_save/totals['baseline']*100:.1f}%)")
    # JSON output for further analysis
    out = ROOT / "tests" / "tokenizer_bench_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results: {out}")

if __name__ == "__main__":
    main()
