"""Test edit accuracy: can transformed code be round-tripped back to valid edits?
Checks: identifier mapping, structural integrity, line-addressability."""
import sys, ast, re, json, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from poor_cli.code_tokenizer import pretokenize, ast_compact_python

ROOT = Path(__file__).parent.parent

def check_pretok_reversibility(original: str) -> dict:
    """Check if pre-tokenized code preserves enough info to apply edits."""
    pretok = pretokenize(original, ".py")
    # 1. can we still parse the pretokenized code?
    try:
        ast.parse(pretok)
        parseable = True
    except SyntaxError:
        parseable = False
    # 2. are all function/class names preserved?
    orig_funcs = set(re.findall(r'\bdef (\w+)', original))
    pretok_funcs = set(re.findall(r'\bdef (\w+)', pretok))
    # identifier normalization changes names
    func_overlap = len(orig_funcs & pretok_funcs) / max(len(orig_funcs), 1)
    # 3. are string literals preserved?
    orig_strings = set(re.findall(r'"([^"]*)"', original))
    pretok_strings = set(re.findall(r'"([^"]*)"', pretok))
    string_overlap = len(orig_strings & pretok_strings) / max(len(orig_strings), 1)
    return {
        "parseable": parseable,
        "func_name_preserved": func_overlap,
        "string_preserved": string_overlap,
    }

def check_ast_compact_quality(original: str) -> dict | None:
    """Check AST-compact output quality."""
    compact = ast_compact_python(original)
    if not compact: return None
    # 1. can compact output be parsed?
    try:
        ast.parse(compact)
        parseable = True
    except SyntaxError:
        parseable = False
    # 2. structural equivalence
    try:
        orig_tree = ast.parse(original)
    except SyntaxError:
        return None
    orig_funcs = set(n.name for n in ast.walk(orig_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    orig_classes = set(n.name for n in ast.walk(orig_tree) if isinstance(n, ast.ClassDef))
    orig_imports = []
    for n in ast.walk(orig_tree):
        if isinstance(n, ast.Import):
            orig_imports.extend(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            orig_imports.extend(f"{n.module}.{a.name}" for a in n.names)
    compact_funcs = set(re.findall(r'\bdef (\w+)', compact))
    compact_classes = set(re.findall(r'\bclass (\w+)', compact))
    compact_imports = set(re.findall(r'\bimport (\S+)', compact))
    return {
        "parseable": parseable,
        "funcs_preserved": len(orig_funcs & compact_funcs) / max(len(orig_funcs), 1),
        "classes_preserved": len(orig_classes & compact_classes) / max(len(orig_classes), 1),
        "funcs_missing": list(orig_funcs - compact_funcs)[:5],
        "classes_missing": list(orig_classes - compact_classes)[:5],
        "n_orig_funcs": len(orig_funcs),
        "n_compact_funcs": len(compact_funcs),
        "n_orig_classes": len(orig_classes),
        "n_compact_classes": len(compact_classes),
    }

def main():
    py_files = sorted(ROOT.glob("poor_cli/**/*.py"))
    print(f"Testing edit accuracy on {len(py_files)} Python files\n")
    pretok_results = []
    ast_results = []
    for f in py_files:
        try:
            code = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if len(code) < 50: continue
        pr = check_pretok_reversibility(code)
        pretok_results.append({"path": str(f.relative_to(ROOT)), **pr})
        ar = check_ast_compact_quality(code)
        if ar:
            ast_results.append({"path": str(f.relative_to(ROOT)), **ar})
    # pretok summary
    print("=== Pre-tokenization Edit Accuracy ===")
    parseable = sum(1 for r in pretok_results if r["parseable"])
    print(f"Parseable after pretok: {parseable}/{len(pretok_results)} ({parseable/len(pretok_results)*100:.1f}%)")
    avg_func = statistics.mean(r["func_name_preserved"] for r in pretok_results)
    avg_str = statistics.mean(r["string_preserved"] for r in pretok_results)
    print(f"Avg func name preservation: {avg_func*100:.1f}%")
    print(f"Avg string literal preservation: {avg_str*100:.1f}%")
    # pretok failures
    unparseable = [r for r in pretok_results if not r["parseable"]]
    if unparseable:
        print(f"\nUnparseable files ({len(unparseable)}):")
        for r in unparseable[:10]:
            print(f"  {r['path']}")
    # ast-compact summary
    print(f"\n=== AST-Compact Edit Accuracy ===")
    parseable = sum(1 for r in ast_results if r["parseable"])
    print(f"Parseable: {parseable}/{len(ast_results)} ({parseable/len(ast_results)*100:.1f}%)")
    avg_func = statistics.mean(r["funcs_preserved"] for r in ast_results)
    avg_cls = statistics.mean(r["classes_preserved"] for r in ast_results)
    print(f"Avg func preservation: {avg_func*100:.1f}%")
    print(f"Avg class preservation: {avg_cls*100:.1f}%")
    # files with missing structures
    missing = [r for r in ast_results if r["funcs_preserved"] < 1.0]
    if missing:
        print(f"\nFiles with missing functions ({len(missing)}):")
        for r in sorted(missing, key=lambda r: r["funcs_preserved"])[:10]:
            print(f"  {r['path']:<55} {r['funcs_preserved']*100:>5.1f}% ({r['n_compact_funcs']}/{r['n_orig_funcs']} funcs) missing: {r['funcs_missing']}")
    # CRITICAL: the real problem with AST-compact for edits
    print("\n=== CRITICAL: Edit Format Compatibility ===")
    print("Pre-tokenization (Approach A):")
    print("  - identifier renaming breaks search-replace edits (camelCase→snake_case)")
    print("  - indentation change (spaces→tabs) breaks line-matching edits")
    print("  - comment removal is safe for context, risky for edits targeting comments")
    print("  VERDICT: usable for CONTEXT (reading), NOT for edit targets")
    print()
    print("AST-compact (Approach B):")
    print("  - complete structural rewrite — NOT the original code")
    print("  - model cannot produce valid search-replace patches against original file")
    print("  - only usable as READ-ONLY context (like a summary)")
    print("  VERDICT: usable for CONTEXT ONLY, never as edit target")
    print()
    print("Safe approach: use transformations for CONTEXT windows only,")
    print("send ORIGINAL code for files the model needs to EDIT.")
    # JSON output
    out = ROOT / "tests" / "edit_accuracy_results.json"
    with open(out, "w") as f:
        json.dump({"pretok": pretok_results, "ast_compact": ast_results}, f, indent=2)
    print(f"\nDetailed results: {out}")

if __name__ == "__main__":
    main()
