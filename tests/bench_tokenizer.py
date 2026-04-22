"""Benchmark tokenization overhead on poor-cli codebase."""
import sys, os, json, re, ast, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import tiktoken

ROOT = Path(__file__).parent.parent
ENC_CL100K = tiktoken.get_encoding("cl100k_base") # gpt-4/claude
ENC_O200K = tiktoken.get_encoding("o200k_base") # gpt-4o

def measure_file(path: Path, enc) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if len(text) < 50: return None # skip trivial files
    tokens = enc.encode(text, disallowed_special=())
    chars = len(text)
    words = len(text.split())
    lines = text.count("\n") + 1
    non_ws_chars = len(re.sub(r'\s', '', text))
    indent_chars = sum(len(line) - len(line.lstrip()) for line in text.splitlines())
    comment_lines = 0
    blank_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped: blank_lines += 1
        elif stripped.startswith("#") or stripped.startswith("--") or stripped.startswith("//"): comment_lines += 1
    return {
        "path": str(path.relative_to(ROOT)),
        "lang": path.suffix,
        "tokens": len(tokens),
        "chars": chars,
        "words": words,
        "lines": lines,
        "tokens_per_word": len(tokens) / words if words else 0,
        "tokens_per_line": len(tokens) / lines if lines else 0,
        "chars_per_token": chars / len(tokens) if tokens else 0,
        "indent_ratio": indent_chars / chars if chars else 0,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
    }

def english_baseline(enc) -> dict:
    """Measure tokens/word for representative English text."""
    text = """The quick brown fox jumps over the lazy dog. This is a sample of natural
English text that should tokenize efficiently with a standard BPE tokenizer. The ratio
of tokens to words in well-formed English prose typically falls between 1.2 and 1.4
tokens per word, depending on vocabulary complexity and the specific tokenizer used.
Software engineering involves designing, developing, testing, and maintaining software
applications. It requires knowledge of programming languages, algorithms, data structures,
and system design principles. Modern software development practices include agile
methodologies, continuous integration, and automated testing frameworks."""
    tokens = enc.encode(text, disallowed_special=())
    words = len(text.split())
    return {"tokens": len(tokens), "words": words, "tokens_per_word": len(tokens)/words}

def collect_files():
    py_files = sorted(ROOT.glob("poor_cli/**/*.py"))
    test_files = sorted(ROOT.glob("tests/test_*.py"))[:10] # sample tests
    return py_files + test_files

def main():
    files = collect_files()
    print(f"Scanning {len(files)} files...\n")
    for enc_name, enc in [("cl100k_base (GPT-4/Claude)", ENC_CL100K), ("o200k_base (GPT-4o)", ENC_O200K)]:
        print(f"=== Encoding: {enc_name} ===")
        eng = english_baseline(enc)
        print(f"English baseline: {eng['tokens_per_word']:.3f} tokens/word\n")
        results = []
        for f in files:
            r = measure_file(f, enc)
            if r: results.append(r)
        by_lang = {}
        for r in results:
            by_lang.setdefault(r["lang"], []).append(r)
        print(f"{'Lang':<6} {'Files':>5} {'Avg tok/word':>13} {'Med tok/word':>13} {'Avg tok/line':>13} {'Avg chr/tok':>12} {'Overhead vs Eng':>16}")
        print("-" * 90)
        all_tpw = []
        for lang, items in sorted(by_lang.items()):
            tpw = [i["tokens_per_word"] for i in items]
            tpl = [i["tokens_per_line"] for i in items]
            cpt = [i["chars_per_token"] for i in items]
            avg_tpw = statistics.mean(tpw)
            med_tpw = statistics.median(tpw)
            avg_tpl = statistics.mean(tpl)
            avg_cpt = statistics.mean(cpt)
            overhead = avg_tpw / eng["tokens_per_word"]
            all_tpw.extend(tpw)
            print(f"{lang:<6} {len(items):>5} {avg_tpw:>13.3f} {med_tpw:>13.3f} {avg_tpl:>13.2f} {avg_cpt:>12.2f} {overhead:>15.2f}x")
        print("-" * 90)
        overall_avg = statistics.mean(all_tpw)
        overall_med = statistics.median(all_tpw)
        overall_overhead = overall_avg / eng["tokens_per_word"]
        print(f"{'ALL':<6} {len(results):>5} {overall_avg:>13.3f} {overall_med:>13.3f} {'':>13} {'':>12} {overall_overhead:>15.2f}x")
        # top 10 worst offenders
        results_sorted = sorted(results, key=lambda r: r["tokens_per_word"], reverse=True)
        print(f"\nTop 10 highest token/word ratio:")
        for r in results_sorted[:10]:
            print(f"  {r['path']:<60} {r['tokens_per_word']:.3f} tok/w  ({r['tokens']} tokens)")
        # indent analysis
        indent_ratios = [r["indent_ratio"] for r in results]
        print(f"\nIndentation overhead: avg {statistics.mean(indent_ratios)*100:.1f}% of chars are indentation")
        total_tokens = sum(r["tokens"] for r in results)
        total_chars = sum(r["chars"] for r in results)
        print(f"Total: {total_tokens:,} tokens across {total_chars:,} chars ({len(results)} files)")
        print()

if __name__ == "__main__":
    main()
