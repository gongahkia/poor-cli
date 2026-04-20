from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from seuss.utils import stable_hash


WORD_RE = re.compile(r"\b\w+\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
PHRASE_SPLIT_RE = re.compile(r"[,;:]+\s*")


@dataclass
class GenerationResult:
    output: str
    level: str
    exact_copy_hits: int
    repetition_score: float


class MarkovModel:
    def __init__(self, order: int) -> None:
        self.order = max(1, order)
        self.start = "<s>"
        self.end = "<eos>"
        self.transitions: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)

    def train(self, sequence: list[str]) -> None:
        if not sequence:
            return
        padded = [self.start] * self.order + sequence + [self.end]
        for idx in range(self.order, len(padded)):
            context = tuple(padded[idx - self.order : idx])
            nxt = padded[idx]
            self.transitions[context][nxt] += 1

    def _choose_weighted(
        self, options: Counter[str], temperature: float, rng: random.Random
    ) -> str:
        if temperature <= 0:
            temperature = 1e-6
        items = list(options.items())
        words = [word for word, _ in items]
        weights = [count for _, count in items]
        scaled = [pow(weight, 1.0 / temperature) for weight in weights]
        total = sum(scaled)
        if total <= 0:
            return words[0]
        roll = rng.random() * total
        upto = 0.0
        for word, weight in zip(words, scaled):
            upto += weight
            if upto >= roll:
                return word
        return words[-1]

    def generate(
        self,
        prompt_tokens: list[str],
        max_tokens: int,
        temperature: float,
        rng: random.Random,
    ) -> list[str]:
        generated: list[str] = []
        seed = prompt_tokens[-self.order :] if prompt_tokens else []
        context = tuple(([self.start] * (self.order - len(seed))) + seed)

        for _ in range(max_tokens):
            options = self.transitions.get(context)
            if not options:
                break
            nxt = self._choose_weighted(options, temperature, rng)
            if nxt == self.end:
                break
            generated.append(nxt)
            context = tuple((list(context) + [nxt])[-self.order :])
        return generated


def tokenize_words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def split_sentences(text: str) -> list[str]:
    chunks = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    return chunks or ([text.strip()] if text.strip() else [])


def split_phrases(text: str) -> list[str]:
    chunks = [part.strip() for part in PHRASE_SPLIT_RE.split(text) if part.strip()]
    return chunks or ([text.strip()] if text.strip() else [])


def repetition_score(text: str) -> float:
    tokens = tokenize_words(text.lower())
    if not tokens:
        return 0.0
    unique = len(set(tokens))
    return max(0.0, 1.0 - (unique / len(tokens)))


def _word_ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    if n <= 0 or len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def exact_copy_hits(text: str, corpus_texts: Iterable[str], n: int) -> int:
    candidate_words = tokenize_words(text.lower())
    cand_ngrams = _word_ngrams(candidate_words, n)
    if not cand_ngrams:
        return 0
    corpus_ngrams: set[tuple[str, ...]] = set()
    for corpus_text in corpus_texts:
        corpus_ngrams.update(_word_ngrams(tokenize_words(corpus_text.lower()), n))
    return len(cand_ngrams & corpus_ngrams)


def _build_char_model(fragments: list[dict], order: int) -> MarkovModel:
    model = MarkovModel(order=order)
    for fragment in fragments:
        chars = list(fragment.get("text", ""))
        model.train(chars)
    return model


def _build_word_model(fragments: list[dict], order: int) -> MarkovModel:
    model = MarkovModel(order=order)
    for fragment in fragments:
        words = tokenize_words(fragment.get("text", ""))
        model.train(words)
    return model


def _build_phrase_model(fragments: list[dict], order: int) -> MarkovModel:
    model = MarkovModel(order=order)
    for fragment in fragments:
        for sentence in split_sentences(fragment.get("text", "")):
            phrases = split_phrases(sentence)
            model.train(phrases)
    return model


def _build_sentence_model(fragments: list[dict], order: int) -> MarkovModel:
    model = MarkovModel(order=order)
    for fragment in fragments:
        sentences = split_sentences(fragment.get("text", ""))
        model.train(sentences)
    return model


def _sentence_stem(text: str, width: int = 3) -> str:
    words = tokenize_words(text.lower())
    if not words:
        return ""
    return " ".join(words[:width])


def _build_motif_model(fragments: list[dict], order: int) -> MarkovModel:
    model = MarkovModel(order=order)
    for fragment in fragments:
        motifs = []
        for sentence in split_sentences(fragment.get("text", "")):
            stem = _sentence_stem(sentence)
            if stem:
                motifs.append(stem)
        model.train(motifs)
    return model


def _format_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
    if text[-1] not in ".!?":
        text += "."
    return text


def _generate_hybrid_discourse(
    prompt: str,
    word_model: MarkovModel,
    phrase_model: MarkovModel,
    sentence_model: MarkovModel,
    motif_model: MarkovModel,
    max_tokens: int,
    temperature: float,
    rng: random.Random,
) -> str:
    target_sentences = max(1, min(8, math.ceil(max_tokens / 18)))

    prompt_sentences = split_sentences(prompt)
    prompt_motifs = [stem for stem in (_sentence_stem(s) for s in prompt_sentences) if stem]

    sentence_units = sentence_model.generate(
        prompt_tokens=prompt_sentences,
        max_tokens=target_sentences,
        temperature=temperature,
        rng=rng,
    )
    motif_units = motif_model.generate(
        prompt_tokens=prompt_motifs,
        max_tokens=target_sentences,
        temperature=temperature,
        rng=rng,
    )

    word_units = word_model.generate(
        prompt_tokens=tokenize_words(prompt),
        max_tokens=max_tokens,
        temperature=temperature,
        rng=rng,
    )

    output_sentences: list[str] = []
    word_cursor = 0

    for idx in range(target_sentences):
        base_sentence = sentence_units[idx].strip() if idx < len(sentence_units) else ""

        if not base_sentence:
            chunk = word_units[word_cursor : word_cursor + 12]
            word_cursor += len(chunk)
            base_sentence = " ".join(chunk).strip()

        motif = motif_units[idx].strip() if idx < len(motif_units) else ""
        if motif and not base_sentence.lower().startswith(motif.lower()):
            base_sentence = f"{motif} {base_sentence}".strip()

        phrase_seed = split_phrases(base_sentence if base_sentence else prompt)
        phrase_tail = phrase_model.generate(
            prompt_tokens=phrase_seed,
            max_tokens=1,
            temperature=temperature,
            rng=rng,
        )
        if phrase_tail:
            tail = phrase_tail[0].strip()
            if tail and tail.lower() not in base_sentence.lower():
                base_sentence = f"{base_sentence}, {tail}"

        formatted = _format_sentence(base_sentence)
        if formatted:
            output_sentences.append(formatted)

    if output_sentences:
        return " ".join(output_sentences)

    return " ".join(word_units).strip()


def _generate_level(
    level: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    rng: random.Random,
    char_model: MarkovModel,
    word_model: MarkovModel,
    phrase_model: MarkovModel,
    sentence_model: MarkovModel,
    motif_model: MarkovModel,
) -> str:
    if level == "character":
        output = char_model.generate(list(prompt), max_tokens, temperature, rng)
        return "".join(output).strip()

    if level == "word":
        output = word_model.generate(tokenize_words(prompt), max_tokens, temperature, rng)
        return " ".join(output).strip()

    if level == "phrase":
        output = phrase_model.generate(split_phrases(prompt), max_tokens, temperature, rng)
        return ", ".join(output).strip()

    return _generate_hybrid_discourse(
        prompt=prompt,
        word_model=word_model,
        phrase_model=phrase_model,
        sentence_model=sentence_model,
        motif_model=motif_model,
        max_tokens=max_tokens,
        temperature=temperature,
        rng=rng,
    )


def generate_text(
    level: str,
    prompt: str,
    fragments: list[dict],
    max_tokens: int,
    temperature: float,
    seed: int,
    anti_copy_ngram: int,
    attempts: int = 3,
    orders: dict[str, int] | None = None,
) -> GenerationResult:
    if not fragments:
        return GenerationResult(output="", level=level, exact_copy_hits=0, repetition_score=0.0)

    order_cfg = {
        "character": 5,
        "word": 3,
        "phrase": 2,
        "sentence": 1,
        "motif": 2,
    }
    if orders:
        for key, value in orders.items():
            if key in order_cfg and isinstance(value, int) and value > 0:
                order_cfg[key] = value

    rng = random.Random(seed)

    char_model = _build_char_model(fragments, order_cfg["character"])
    word_model = _build_word_model(fragments, order_cfg["word"])
    phrase_model = _build_phrase_model(fragments, order_cfg["phrase"])
    sentence_model = _build_sentence_model(fragments, order_cfg["sentence"])
    motif_model = _build_motif_model(fragments, order_cfg["motif"])

    best_output = ""
    best_hits = 10**9
    corpus_texts = [fragment.get("text", "") for fragment in fragments]

    for _ in range(max(1, attempts)):
        output = _generate_level(
            level=level,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            rng=rng,
            char_model=char_model,
            word_model=word_model,
            phrase_model=phrase_model,
            sentence_model=sentence_model,
            motif_model=motif_model,
        ).strip()

        hits = exact_copy_hits(output, corpus_texts, anti_copy_ngram)
        if hits < best_hits:
            best_output = output
            best_hits = hits
        if hits == 0:
            break
        # Nudge RNG so retries do not replay the same branch.
        rng.seed(int(stable_hash([seed, output])[:8], 16))

    return GenerationResult(
        output=best_output,
        level=level,
        exact_copy_hits=0 if best_hits == 10**9 else best_hits,
        repetition_score=repetition_score(best_output),
    )
