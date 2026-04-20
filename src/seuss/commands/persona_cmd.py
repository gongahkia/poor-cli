from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jugemu import split_sentences, tokenize_words
from seuss.jsonl_store import read_jsonl
from seuss.utils import now_iso, stable_hash


def _avg_sentence_words(texts: list[str]) -> float:
    sentence_lengths: list[int] = []
    for text in texts:
        for sentence in split_sentences(text):
            words = tokenize_words(sentence)
            if words:
                sentence_lengths.append(len(words))
    if not sentence_lengths:
        return 0.0
    return sum(sentence_lengths) / len(sentence_lengths)


def _sentence_style_bucket(avg_words: float) -> str:
    if avg_words < 8:
        return "short"
    if avg_words <= 16:
        return "medium"
    return "long"


def _top_words(texts: list[str], limit: int = 40) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(tokenize_words(text.lower()))
    return [word for word, _ in counts.most_common(limit)]


def _top_phrases(fragments: list[dict], limit: int = 30) -> list[str]:
    phrase_rows = [row for row in fragments if row.get("segment_type") == "phrase"]
    counts = Counter(row.get("normalized_text", "") for row in phrase_rows)
    return [phrase for phrase, _ in counts.most_common(limit) if phrase]


def _punctuation_profile(texts: list[str]) -> dict[str, int]:
    profile = {"question_marks": 0, "exclamations": 0, "commas": 0, "semicolons": 0}
    for text in texts:
        profile["question_marks"] += text.count("?")
        profile["exclamations"] += text.count("!")
        profile["commas"] += text.count(",")
        profile["semicolons"] += text.count(";")
    return profile


def run_persona_build(config_path: Path, output_path: Path | None = None) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
    memories = read_jsonl(workspace / "memory" / "memories.jsonl")

    if not fragments:
        print("No corpus fragments found. Run 'seuss ingest' first.")
        return 1

    train_fragments = [row for row in fragments if row.get("split") == "train"]
    source_texts = [row.get("text", "") for row in train_fragments]

    avg_words = _avg_sentence_words(source_texts)
    style_bucket = _sentence_style_bucket(avg_words)
    top_words = _top_words(source_texts)
    top_phrases = _top_phrases(train_fragments)
    punctuation = _punctuation_profile(source_texts)

    style_memories = [
        row.get("text", "")
        for row in memories
        if row.get("kind") in {"style", "conversation"} and row.get("text")
    ]

    profile = {
        "id": f"persona_{stable_hash([now_iso(), len(train_fragments), len(memories)])[:12]}",
        "created_at": now_iso(),
        "config_hash": f"sha256:{stable_hash(config)}",
        "corpus": {
            "train_fragment_count": len(train_fragments),
            "memory_count": len(memories),
            "sources": sorted({row.get("source", "unknown") for row in train_fragments}),
        },
        "voice": {
            "sentence_length_avg_words": round(avg_words, 3),
            "sentence_length_bucket": style_bucket,
            "punctuation": punctuation,
        },
        "lexical": {
            "top_words": top_words,
            "top_phrases": top_phrases,
        },
        "memory_hints": style_memories[:30],
    }

    if output_path is None:
        output_path = workspace / "memory" / "persona_profile.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"Persona profile written: {output_path}")
    print(f"sentence_length_bucket={profile['voice']['sentence_length_bucket']}")
    print(f"top_words={len(profile['lexical']['top_words'])} top_phrases={len(profile['lexical']['top_phrases'])}")
    return 0


def run_persona_show(config_path: Path, input_path: Path | None = None) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    if input_path is None:
        input_path = workspace / "memory" / "persona_profile.json"

    if not input_path.exists():
        print(f"Persona profile not found: {input_path}")
        return 1

    profile = json.loads(input_path.read_text(encoding="utf-8"))
    print(f"id={profile.get('id')}")
    print(f"created_at={profile.get('created_at')}")
    print(f"sentence_length_bucket={profile.get('voice', {}).get('sentence_length_bucket')}")
    print(
        "sources=" + ",".join(profile.get("corpus", {}).get("sources", []))
    )

    words = profile.get("lexical", {}).get("top_words", [])
    phrases = profile.get("lexical", {}).get("top_phrases", [])
    if words:
        print("top_words=" + ", ".join(words[:10]))
    if phrases:
        print("top_phrases=" + " | ".join(phrases[:5]))

    return 0
