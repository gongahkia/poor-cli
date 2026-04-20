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


def _generate_level(
    level: str,
    prompt: str,
    fragments: list[dict],
    orders: dict[str, int],
    max_tokens: int,
    temperature: float,
    rng: random.Random,
) -> str:
    if level == "character":
        model = _build_char_model(fragments, orders["character"])
        output = model.generate(list(prompt), max_tokens, temperature, rng)
        return "".join(output).strip()

    if level == "word":
        model = _build_word_model(fragments, orders["word"])
        output = model.generate(tokenize_words(prompt), max_tokens, temperature, rng)
        return " ".join(output).strip()

    if level == "phrase":
        model = _build_phrase_model(fragments, orders["phrase"])
        output = model.generate(split_phrases(prompt), max_tokens, temperature, rng)
        return ", ".join(output).strip()

    # Hybrid: word-first body with phrase tail when phrase data exists.
    word_model = _build_word_model(fragments, orders["word"])
    phrase_model = _build_phrase_model(fragments, orders["phrase"])
    body = word_model.generate(tokenize_words(prompt), max_tokens, temperature, rng)
    tail = phrase_model.generate(split_phrases(prompt), max(2, math.floor(max_tokens / 6)), temperature, rng)
    body_text = " ".join(body).strip()
    tail_text = ", ".join(tail).strip()
    if body_text and tail_text:
        return f"{body_text}. {tail_text}"
    return body_text or tail_text


def generate_text(
    level: str,
    prompt: str,
    fragments: list[dict],
    max_tokens: int,
    temperature: float,
    seed: int,
    anti_copy_ngram: int,
    attempts: int = 3,
) -> GenerationResult:
    if not fragments:
        return GenerationResult(output="", level=level, exact_copy_hits=0, repetition_score=0.0)

    rng = random.Random(seed)
    orders = {
        "character": 5,
        "word": 3,
        "phrase": 2,
    }

    best_output = ""
    best_hits = 10**9
    corpus_texts = [fragment.get("text", "") for fragment in fragments]

    for _ in range(max(1, attempts)):
        output = _generate_level(
            level=level,
            prompt=prompt,
            fragments=fragments,
            orders=orders,
            max_tokens=max_tokens,
            temperature=temperature,
            rng=rng,
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
