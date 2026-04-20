from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jugemu import exact_copy_hits, generate_text, repetition_score, tokenize_words
from seuss.jsonl_store import read_jsonl
from seuss.utils import now_iso, stable_hash

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{7,}\d")


def _top_words(texts: list[str], limit: int = 200) -> set[str]:
    counts = Counter()
    for text in texts:
        counts.update(tokenize_words(text.lower()))
    return {word for word, _ in counts.most_common(limit)}


def _persona_match_score(generated: list[str], heldout: list[str]) -> float:
    g_words = _top_words(generated)
    h_words = _top_words(heldout)
    if not g_words and not h_words:
        return 1.0
    if not g_words or not h_words:
        return 0.0
    return len(g_words & h_words) / len(g_words | h_words)


def _privacy_leak_count(outputs: list[str]) -> int:
    count = 0
    for output in outputs:
        if EMAIL_RE.search(output) or PHONE_RE.search(output):
            count += 1
    return count


def run_eval(
    config_path: Path,
    suite: str,
    seed: int | None,
    output_path: Path | None,
) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
    train_fragments = [row for row in fragments if row.get("split") == "train"]
    eval_fragments = [row for row in fragments if row.get("split") == "eval"]

    heldout_required = bool(config.get("evaluation", {}).get("heldout_required", True))
    if heldout_required and not eval_fragments:
        print("Evaluation requires held-out fragments, but none were found.")
        return 1
    if not train_fragments:
        print("No train fragments found. Run 'seuss ingest' first.")
        return 1

    eval_cfg = config.get("evaluation", {})
    generation_cfg = config.get("generation", {})
    jugemu_cfg = generation_cfg.get("jugemu", {})

    chosen_seed = int(seed if seed is not None else generation_cfg.get("seed", 42))
    level = generation_cfg.get("default_level", "hybrid")
    max_tokens = int(generation_cfg.get("max_tokens", 120))
    temperature = float(generation_cfg.get("temperature", 0.8))
    exact_copy_ngram = int(eval_cfg.get("exact_copy_ngram", 12))
    anti_copy_ngram = int(jugemu_cfg.get("anti_copy_ngram", 12))

    prompts: list[str] = []
    for row in eval_fragments[: min(50, len(eval_fragments))]:
        words = tokenize_words(row.get("text", ""))
        prompt = " ".join(words[: min(4, len(words))]).strip()
        if prompt:
            prompts.append(prompt)
    if not prompts:
        prompts = ["I think", "In practice", "The tradeoff is"]

    outputs: list[str] = []
    copy_hits_total = 0
    repetition_scores: list[float] = []

    source_texts = [row.get("text", "") for row in fragments]
    for idx, prompt in enumerate(prompts):
        result = generate_text(
            level=level,
            prompt=prompt,
            fragments=train_fragments,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=chosen_seed + idx,
            anti_copy_ngram=anti_copy_ngram,
        )
        outputs.append(result.output)
        copy_hits_total += exact_copy_hits(result.output, source_texts, exact_copy_ngram)
        repetition_scores.append(repetition_score(result.output))

    heldout_texts = [row.get("text", "") for row in eval_fragments]
    persona_score = _persona_match_score(outputs, heldout_texts)
    exact_copy_rate = copy_hits_total / max(1, len(outputs))
    avg_repetition = sum(repetition_scores) / max(1, len(repetition_scores))
    privacy_leak_count = _privacy_leak_count(outputs)

    report = {
        "id": f"eval_{now_iso().replace(':', '').replace('-', '')}",
        "suite": suite,
        "created_at": now_iso(),
        "config_hash": f"sha256:{stable_hash(config)}",
        "metrics": {
            "persona_match_score": round(persona_score, 6),
            "exact_copy_rate": round(exact_copy_rate, 6),
            "repetition_score": round(avg_repetition, 6),
            "privacy_leak_count": privacy_leak_count,
            "num_samples": len(outputs),
        },
        "samples": [
            {"prompt": prompt, "output": output}
            for prompt, output in zip(prompts[:10], outputs[:10])
        ],
    }

    final_output_path = output_path
    if final_output_path is None:
        report_dir = Path(eval_cfg.get("report_path", str(workspace / "evals")))
        if not report_dir.is_absolute():
            report_dir = (config_path.parent / report_dir).resolve()
        report_dir.mkdir(parents=True, exist_ok=True)
        final_output_path = report_dir / f"{report['id']}.json"
    else:
        final_output_path.parent.mkdir(parents=True, exist_ok=True)

    final_output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"suite={suite}")
    print(
        "persona_match_score="
        f"{report['metrics']['persona_match_score']:.4f} "
        f"exact_copy_rate={report['metrics']['exact_copy_rate']:.4f} "
        f"repetition_score={report['metrics']['repetition_score']:.4f} "
        f"privacy_leak_count={report['metrics']['privacy_leak_count']}"
    )
    print(f"Report: {final_output_path}")

    return 0
