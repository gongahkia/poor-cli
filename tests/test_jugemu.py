import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.jugemu import exact_copy_hits, generate_text, split_sentences


class JugemuTests(unittest.TestCase):
    def test_hybrid_generation_returns_discourse_like_text(self) -> None:
        fragments = [
            {
                "text": "I think clear boundaries matter. In practice we test assumptions early. The tradeoff is speed versus certainty."
            },
            {
                "text": "I think we should start small. In practice iterate and evaluate. The tradeoff is complexity versus control."
            },
        ]

        result = generate_text(
            level="hybrid",
            prompt="I think",
            fragments=fragments,
            max_tokens=64,
            temperature=0.8,
            seed=7,
            anti_copy_ngram=10,
            orders={"sentence": 1, "motif": 2},
        )

        self.assertTrue(result.output)
        self.assertGreaterEqual(len(split_sentences(result.output)), 1)
        self.assertTrue(any(punct in result.output for punct in ".!?"))

    def test_exact_copy_hits_detects_shared_ngrams(self) -> None:
        output = "clear boundaries matter in practice"
        corpus = ["we learned that clear boundaries matter in practice"]
        self.assertGreater(exact_copy_hits(output, corpus, n=3), 0)


if __name__ == "__main__":
    unittest.main()
