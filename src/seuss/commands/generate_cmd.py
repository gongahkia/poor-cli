from __future__ import annotations

import json
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jugemu import generate_text
from seuss.jsonl_store import read_jsonl
from seuss.utils import generate_id, now_iso, stable_hash


def run_generate(
    config_path: Path,
    prompt: str,
    level: str | None,
    max_tokens: int | None,
    temperature: float | None,
    seed: int | None,
    save: bool,
) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
    train_fragments = [row for row in fragments if row.get("split") == "train"]

    if not train_fragments:
        print("No train fragments found. Run 'seuss ingest' first.")
        return 1

    generation_cfg = config.get("generation", {})
    jugemu_cfg = generation_cfg.get("jugemu", {})

    chosen_level = level or generation_cfg.get("default_level", "hybrid")
    chosen_max_tokens = int(max_tokens or generation_cfg.get("max_tokens", 120))
    chosen_temp = float(temperature if temperature is not None else generation_cfg.get("temperature", 0.8))
    chosen_seed = int(seed if seed is not None else generation_cfg.get("seed", 42))
    anti_copy_ngram = int(jugemu_cfg.get("anti_copy_ngram", 12))
    orders = {
        "character": int(jugemu_cfg.get("character_order", 5)),
        "word": int(jugemu_cfg.get("word_order", 3)),
        "phrase": int(jugemu_cfg.get("phrase_order", 2)),
        "sentence": int(jugemu_cfg.get("sentence_order", 1)),
        "motif": int(jugemu_cfg.get("motif_order", 2)),
    }

    result = generate_text(
        level=chosen_level,
        prompt=prompt,
        fragments=train_fragments,
        max_tokens=chosen_max_tokens,
        temperature=chosen_temp,
        seed=chosen_seed,
        anti_copy_ngram=anti_copy_ngram,
        orders=orders,
    )

    print(result.output)
    print(f"level={result.level} exact_copy_hits={result.exact_copy_hits} repetition_score={result.repetition_score:.4f}")

    if save:
        run_id = generate_id("run")
        run_record = {
            "id": run_id,
            "prompt": prompt,
            "output": result.output,
            "level": result.level,
            "config_hash": f"sha256:{stable_hash(config)}",
            "seed": chosen_seed,
            "created_at": now_iso(),
            "metrics": {
                "exact_copy_ngram_hits": result.exact_copy_hits,
                "repetition_score": result.repetition_score,
            },
        }
        run_path = workspace / "runs" / f"{run_id}.json"
        run_path.write_text(json.dumps(run_record, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"Saved run: {run_path}")

    return 0
