from __future__ import annotations

import json
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jugemu import generate_text
from seuss.jsonl_store import read_jsonl
from seuss.utils import generate_id, now_iso, stable_hash


def load_persona_profile(workspace: Path, persona_path: str | None) -> dict | None:
    target = Path(persona_path).expanduser().resolve() if persona_path else workspace / "memory" / "persona_profile.json"
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def augment_prompt_with_persona(prompt: str, persona_profile: dict | None) -> str:
    if not persona_profile:
        return prompt

    lexical = persona_profile.get("lexical", {})
    voice = persona_profile.get("voice", {})
    hints: list[str] = []

    top_phrases = lexical.get("top_phrases", [])
    top_words = lexical.get("top_words", [])
    memory_hints = persona_profile.get("memory_hints", [])
    sentence_bucket = voice.get("sentence_length_bucket")

    if sentence_bucket:
        hints.append(f"style {sentence_bucket}")
    if top_phrases:
        hints.append(" ".join(str(p) for p in top_phrases[:2]))
    if top_words:
        hints.append(" ".join(str(w) for w in top_words[:6]))
    if memory_hints:
        hints.append(str(memory_hints[0]))

    merged = " ".join(part.strip() for part in hints if str(part).strip())
    if not merged:
        return prompt
    if prompt:
        return f"{prompt} {merged}".strip()
    return merged


def run_generate(
    config_path: Path,
    prompt: str,
    level: str | None,
    max_tokens: int | None,
    temperature: float | None,
    seed: int | None,
    save: bool,
    use_persona: bool = False,
    persona_path: str | None = None,
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

    persona_profile = load_persona_profile(workspace, persona_path) if use_persona else None
    if use_persona and persona_profile is None:
        target = persona_path or str(workspace / "memory" / "persona_profile.json")
        print(f"Persona profile not found: {target}")
        print("Run 'seuss persona build' first or pass --persona-path.")
        return 1

    effective_prompt = augment_prompt_with_persona(prompt, persona_profile)

    result = generate_text(
        level=chosen_level,
        prompt=effective_prompt,
        fragments=train_fragments,
        max_tokens=chosen_max_tokens,
        temperature=chosen_temp,
        seed=chosen_seed,
        anti_copy_ngram=anti_copy_ngram,
        orders=orders,
    )

    print(result.output)
    print(f"level={result.level} exact_copy_hits={result.exact_copy_hits} repetition_score={result.repetition_score:.4f}")
    if use_persona and persona_profile:
        print(f"persona_profile_id={persona_profile.get('id', 'unknown')}")

    if save:
        run_id = generate_id("run")
        run_record = {
            "id": run_id,
            "prompt": prompt,
            "effective_prompt": effective_prompt,
            "output": result.output,
            "level": result.level,
            "config_hash": f"sha256:{stable_hash(config)}",
            "seed": chosen_seed,
            "used_persona": use_persona,
            "persona_profile_id": persona_profile.get("id") if persona_profile else None,
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
