from __future__ import annotations

import json
import uuid
from pathlib import Path

from seuss.commands.generate_cmd import augment_prompt_with_persona, load_persona_profile
from seuss.commands.memory_cmd import queue_or_approve_training_examples
from seuss.commands.persona_cmd import run_persona_build
from seuss.config import load_config, resolve_workspace
from seuss.jsonl_store import append_jsonl, read_jsonl
from seuss.jugemu import generate_text
from seuss.utils import now_iso, stable_hash


def _resolve_persona_target(workspace: Path, persona_path: str | None) -> Path:
    if persona_path:
        return Path(persona_path).expanduser().resolve()
    return workspace / "memory" / "persona_profile.json"


def run_chat(
    config_path: Path,
    level: str | None,
    max_tokens: int | None,
    temperature: float | None,
    seed: int | None,
    save: bool,
    use_persona: bool = False,
    persona_path: str | None = None,
    refresh_persona_every: int = 3,
    max_turns: int | None = None,
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
    chosen_temp = float(
        temperature if temperature is not None else generation_cfg.get("temperature", 0.8)
    )
    base_seed = int(seed if seed is not None else generation_cfg.get("seed", 42))
    anti_copy_ngram = int(jugemu_cfg.get("anti_copy_ngram", 12))
    orders = {
        "character": int(jugemu_cfg.get("character_order", 5)),
        "word": int(jugemu_cfg.get("word_order", 3)),
        "phrase": int(jugemu_cfg.get("phrase_order", 2)),
        "sentence": int(jugemu_cfg.get("sentence_order", 1)),
        "motif": int(jugemu_cfg.get("motif_order", 2)),
    }

    memory_path = workspace / "memory" / "memories.jsonl"
    persona_target = _resolve_persona_target(workspace, persona_path)

    print("Seuss chat started. Type /exit to stop.")
    turn = 0

    while True:
        if max_turns is not None and turn >= max_turns:
            print("Reached max turns. Exiting chat.")
            break

        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chat.")
            break

        if not user_text:
            continue
        if user_text.lower() in {"/exit", "/quit", "exit", "quit"}:
            print("Exiting chat.")
            break

        memory_record = {
            "id": f"mem_{uuid.uuid4().hex[:12]}",
            "kind": "conversation",
            "text": user_text,
            "source": "live_chat",
            "provenance": "conversation_live",
            "created_at": now_iso(),
            "confidence": 0.7,
            "approved_for_training": False,
        }
        append_jsonl(memory_path, [memory_record])
        queue_or_approve_training_examples(workspace, config, config_path, [memory_record])
        turn += 1

        persona_profile = None
        if use_persona:
            should_refresh = (
                not persona_target.exists()
                or (refresh_persona_every > 0 and turn % refresh_persona_every == 0)
            )
            if should_refresh:
                run_persona_build(config_path=config_path, output_path=persona_target)
            persona_profile = load_persona_profile(workspace, str(persona_target))

        effective_prompt = augment_prompt_with_persona(user_text, persona_profile)

        memory_rows = read_jsonl(memory_path)
        memory_fragments = [
            {"text": row.get("text", "")}
            for row in memory_rows[-200:]
            if str(row.get("text", "")).strip()
        ]
        generation_fragments = train_fragments + memory_fragments

        result = generate_text(
            level=chosen_level,
            prompt=effective_prompt,
            fragments=generation_fragments,
            max_tokens=chosen_max_tokens,
            temperature=chosen_temp,
            seed=base_seed + turn,
            anti_copy_ngram=anti_copy_ngram,
            orders=orders,
        )
        if not result.output.strip():
            result = generate_text(
                level=chosen_level,
                prompt="",
                fragments=generation_fragments,
                max_tokens=chosen_max_tokens,
                temperature=chosen_temp,
                seed=base_seed + turn + 1,
                anti_copy_ngram=anti_copy_ngram,
                orders=orders,
            )

        assistant_text = result.output.strip() or "..."
        print(f"assistant> {assistant_text}")

        if save:
            run_id = f"run_{now_iso().replace(':', '').replace('-', '')}_{uuid.uuid4().hex[:8]}"
            run_record = {
                "id": run_id,
                "mode": "chat",
                "turn": turn,
                "prompt": user_text,
                "effective_prompt": effective_prompt,
                "output": assistant_text,
                "level": result.level,
                "config_hash": f"sha256:{stable_hash(config)}",
                "seed": base_seed + turn,
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

    return 0
