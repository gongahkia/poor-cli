"""
Benchmark: text-in-context vs neural retrieval for code Q&A.

Tests on poor-cli's own codebase. Measures:
- Token count: how many tokens each approach uses
- Retrieval quality: does neural retrieval surface relevant code?
- Coverage: are the right files/chunks included?

Usage:
    python -m pytest tests/test_neural_encoder.py -v
    python tests/test_neural_encoder.py  # standalone benchmark mode

Requires: pip install transformers torch
"""

from __future__ import annotations
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── test queries with known relevant files ──────────────────────────────

BENCHMARK_QUERIES: List[Dict] = [
    {
        "query": "how does the embedding provider work",
        "expected_files": ["poor_cli/embeddings.py", "poor_cli/indexer.py"],
        "category": "architecture",
    },
    {
        "query": "how are tools registered and dispatched",
        "expected_files": ["poor_cli/tools_async.py", "poor_cli/enhanced_tools.py"],
        "category": "architecture",
    },
    {
        "query": "how does context get assembled for the LLM prompt",
        "expected_files": ["poor_cli/context_engine.py", "poor_cli/context_providers.py"],
        "category": "architecture",
    },
    {
        "query": "fix the config loading to handle missing keys",
        "expected_files": ["poor_cli/config.py", "poor_cli/repo_config.py"],
        "category": "bugfix",
    },
    {
        "query": "add a new MCP server endpoint",
        "expected_files": ["poor_cli/mcp_client.py", "poor_cli/server/runtime.py"],
        "category": "feature",
    },
    {
        "query": "how does AST chunking split code into pieces",
        "expected_files": ["poor_cli/indexer.py"],
        "category": "architecture",
    },
    {
        "query": "optimize token budget for multi-provider routing",
        "expected_files": ["poor_cli/economy.py", "poor_cli/model_router.py", "poor_cli/token_budget_controller.py"],
        "category": "optimization",
    },
    {
        "query": "how does the history get pruned and managed",
        "expected_files": ["poor_cli/history.py", "poor_cli/history_pruning.py"],
        "category": "architecture",
    },
    {
        "query": "implement prompt compression for large contexts",
        "expected_files": ["poor_cli/prompt_compressor.py", "poor_cli/context_optimizer.py"],
        "category": "feature",
    },
    {
        "query": "how do providers translate tool calls between formats",
        "expected_files": ["poor_cli/providers/tool_translator.py", "poor_cli/providers/base.py"],
        "category": "architecture",
    },
]


def _estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return len(text) // 4


def _file_overlap(retrieved_files: List[str], expected_files: List[str]) -> Tuple[float, float]:
    """Compute precision and recall of retrieved files vs expected.

    Returns (precision, recall).
    """
    retrieved_set = set(retrieved_files)
    expected_set = set(expected_files)
    if not retrieved_set:
        return 0.0, 0.0
    hits = retrieved_set & expected_set
    precision = len(hits) / len(retrieved_set) if retrieved_set else 0.0
    recall = len(hits) / len(expected_set) if expected_set else 0.0
    return precision, recall


# ── text-in-context baseline ────────────────────────────────────────────

class TextInContextBaseline:
    """Baseline: stuff all Python files into context as raw text."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def get_context(self, query: str, max_files: int = 12) -> Tuple[str, List[str]]:
        """Return (context_text, file_list) using naive file inclusion."""
        py_files = sorted(self.repo_root.glob("poor_cli/**/*.py"))
        context_parts = []
        included = []
        for f in py_files[:max_files]:
            try:
                content = f.read_text()
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_root))
            context_parts.append(f"## {rel}\n```python\n{content}\n```")
            included.append(rel)
        return "\n\n".join(context_parts), included


# ── neural retrieval approach ───────────────────────────────────────────

class NeuralRetrievalBenchmark:
    """Benchmark wrapper around NeuralCodeRetriever."""

    def __init__(self, repo_root: Path, model_key: str = "unixcoder"):
        self.repo_root = repo_root
        self._model_key = model_key
        self._retriever = None

    async def setup(self) -> Dict:
        """Index the codebase. Returns index stats."""
        from poor_cli.neural_code_encoder import NeuralCodeRetriever
        self._retriever = NeuralCodeRetriever(
            repo_root=self.repo_root,
            model_key=self._model_key,
        )
        return await self._retriever.index_codebase()

    async def get_context(self, query: str, top_k: int = 10) -> Tuple[str, List[str]]:
        """Return (context_text, file_list) using neural retrieval."""
        if self._retriever is None:
            raise RuntimeError("call setup() first")
        results = await self._retriever.retrieve(query, top_k=top_k)
        context = "\n\n".join(r.context_block() for r in results)
        files = list(dict.fromkeys(r.file_path for r in results)) # dedup, preserve order
        return context, files


# ── benchmark runner ────────────────────────────────────────────────────

async def run_benchmark(repo_root: Path, model_key: str = "unixcoder") -> Dict:
    """Run full benchmark: text-in-context vs neural retrieval."""
    print(f"=== Neural Code Embedding Benchmark ===")
    print(f"repo: {repo_root}")
    print(f"model: {model_key}")
    print(f"queries: {len(BENCHMARK_QUERIES)}")
    print()

    # setup
    baseline = TextInContextBaseline(repo_root)
    neural = NeuralRetrievalBenchmark(repo_root, model_key)

    print("indexing codebase for neural retrieval...")
    t0 = time.time()
    index_stats = await neural.setup()
    index_time = time.time() - t0
    print(f"  indexed {index_stats.get('indexed', 0)} chunks in {index_time:.1f}s")
    print()

    results = {
        "model": model_key,
        "index_stats": index_stats,
        "index_time_seconds": round(index_time, 2),
        "queries": [],
        "summary": {},
    }

    baseline_total_tokens = 0
    neural_total_tokens = 0
    baseline_total_recall = 0.0
    neural_total_recall = 0.0
    baseline_total_precision = 0.0
    neural_total_precision = 0.0

    for i, q in enumerate(BENCHMARK_QUERIES):
        query = q["query"]
        expected = q["expected_files"]

        # baseline
        t0 = time.time()
        b_context, b_files = baseline.get_context(query)
        b_time = time.time() - t0
        b_tokens = _estimate_tokens(b_context)
        b_prec, b_rec = _file_overlap(b_files, expected)

        # neural
        t0 = time.time()
        n_context, n_files = await neural.get_context(query)
        n_time = time.time() - t0
        n_tokens = _estimate_tokens(n_context)
        n_prec, n_rec = _file_overlap(n_files, expected)

        token_reduction = 1 - (n_tokens / b_tokens) if b_tokens > 0 else 0
        qr = {
            "query": query,
            "category": q["category"],
            "expected_files": expected,
            "baseline": {
                "tokens": b_tokens,
                "files": b_files[:5], # truncate for readability
                "precision": round(b_prec, 3),
                "recall": round(b_rec, 3),
                "time_ms": round(b_time * 1000, 1),
            },
            "neural": {
                "tokens": n_tokens,
                "files": n_files[:5],
                "precision": round(n_prec, 3),
                "recall": round(n_rec, 3),
                "time_ms": round(n_time * 1000, 1),
            },
            "token_reduction": round(token_reduction, 3),
        }
        results["queries"].append(qr)

        baseline_total_tokens += b_tokens
        neural_total_tokens += n_tokens
        baseline_total_recall += b_rec
        neural_total_recall += n_rec
        baseline_total_precision += b_prec
        neural_total_precision += n_prec

        indicator = "+" if n_rec >= b_rec else "-"
        print(f"  [{indicator}] Q{i+1}: {query[:50]}...")
        print(f"      baseline: {b_tokens:,} tok, recall={b_rec:.2f}")
        print(f"      neural:   {n_tokens:,} tok, recall={n_rec:.2f}, reduction={token_reduction:.1%}")

    n = len(BENCHMARK_QUERIES)
    results["summary"] = {
        "avg_baseline_tokens": baseline_total_tokens // n,
        "avg_neural_tokens": neural_total_tokens // n,
        "avg_token_reduction": round(1 - (neural_total_tokens / baseline_total_tokens), 3) if baseline_total_tokens else 0,
        "avg_baseline_recall": round(baseline_total_recall / n, 3),
        "avg_neural_recall": round(neural_total_recall / n, 3),
        "avg_baseline_precision": round(baseline_total_precision / n, 3),
        "avg_neural_precision": round(neural_total_precision / n, 3),
    }

    print()
    print("=== Summary ===")
    s = results["summary"]
    print(f"  avg tokens — baseline: {s['avg_baseline_tokens']:,}, neural: {s['avg_neural_tokens']:,}")
    print(f"  avg token reduction: {s['avg_token_reduction']:.1%}")
    print(f"  avg recall — baseline: {s['avg_baseline_recall']:.3f}, neural: {s['avg_neural_recall']:.3f}")
    print(f"  avg precision — baseline: {s['avg_baseline_precision']:.3f}, neural: {s['avg_neural_precision']:.3f}")

    return results


# ── standalone benchmark mode ───────────────────────────────────────────

if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    model = sys.argv[1] if len(sys.argv) > 1 else "unixcoder"
    results = asyncio.run(run_benchmark(repo_root, model))
    out_path = repo_root / "tests" / "benchmark_neural_retrieval.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nresults saved to {out_path}")
    sys.exit(0)

# ── pytest tests (only loaded when running via pytest) ──────────────────

import pytest

REPO_ROOT = Path(__file__).parent.parent

@pytest.fixture(scope="module")
def hf_available() -> bool:
    try:
        import torch
        import transformers
        return True
    except ImportError:
        return False


class TestHuggingFaceEmbedding:
    """Unit tests for HuggingFaceCodeEmbedding."""

    def test_available_check(self):
        from poor_cli.neural_code_encoder import HuggingFaceCodeEmbedding
        emb = HuggingFaceCodeEmbedding()
        # should return True/False without crashing
        result = emb.available()
        assert isinstance(result, bool)

    def test_model_registry(self):
        from poor_cli.neural_code_encoder import HF_CODE_MODELS
        assert "codebert" in HF_CODE_MODELS
        assert "unixcoder" in HF_CODE_MODELS
        assert "graphcodebert" in HF_CODE_MODELS

    @pytest.mark.skipif(
        not (lambda: __import__("torch") and __import__("transformers") and True)(),
        reason="torch/transformers not installed",
    )
    def test_embed_produces_vectors(self):
        from poor_cli.neural_code_encoder import HuggingFaceCodeEmbedding
        emb = HuggingFaceCodeEmbedding(model_key="codebert")
        texts = ["def hello(): pass", "class Foo: pass"]
        vecs = asyncio.run(emb.embed(texts))
        assert len(vecs) == 2
        assert len(vecs[0]) == 768 # codebert dim
        # verify L2 normalized
        norm = math.sqrt(sum(x*x for x in vecs[0]))
        assert abs(norm - 1.0) < 0.01

    @pytest.mark.skipif(
        not (lambda: __import__("torch") and __import__("transformers") and True)(),
        reason="torch/transformers not installed",
    )
    def test_code_similarity_sanity(self):
        """Similar code should have higher similarity than dissimilar code."""
        from poor_cli.neural_code_encoder import HuggingFaceCodeEmbedding
        from poor_cli.embeddings import cosine_similarity
        emb = HuggingFaceCodeEmbedding(model_key="codebert")
        texts = [
            "def add(a, b): return a + b",        # [0] arithmetic
            "def subtract(a, b): return a - b",    # [1] arithmetic (similar to [0])
            "class DatabaseConnection: pass",      # [2] unrelated
        ]
        vecs = asyncio.run(emb.embed(texts))
        sim_01 = cosine_similarity(vecs[0], vecs[1]) # add vs subtract
        sim_02 = cosine_similarity(vecs[0], vecs[2]) # add vs database
        assert sim_01 > sim_02, f"similar code should score higher: {sim_01:.3f} vs {sim_02:.3f}"


class TestNeuralRetriever:
    """Integration tests for NeuralCodeRetriever."""

    @pytest.mark.skipif(
        not (lambda: __import__("torch") and __import__("transformers") and True)(),
        reason="torch/transformers not installed",
    )
    def test_retrieve_returns_results(self):
        from poor_cli.neural_code_encoder import NeuralCodeRetriever
        async def _run():
            retriever = NeuralCodeRetriever(repo_root=REPO_ROOT, model_key="codebert")
            stats = await retriever.index_codebase()
            assert stats.get("indexed", 0) > 0
            results = await retriever.retrieve("embedding provider")
            assert len(results) > 0
            files = [r.file_path for r in results]
            return files
        files = asyncio.run(_run())


class TestCodebaseProjection:
    """Tests for the LLaVA-style projection prototype."""

    @pytest.mark.skipif(
        not (lambda: __import__("torch") and True)(),
        reason="torch not installed",
    )
    def test_projection_builds(self):
        from poor_cli.neural_code_encoder import CodebaseProjection
        proj = CodebaseProjection(code_dim=768, llm_dim=4096, num_tokens=32)
        proj.build()
        assert proj.parameter_count() > 0

    @pytest.mark.skipif(
        not (lambda: __import__("torch") and True)(),
        reason="torch not installed",
    )
    def test_projection_forward(self):
        import torch
        from poor_cli.neural_code_encoder import CodebaseProjection
        proj = CodebaseProjection(code_dim=768, llm_dim=4096, num_tokens=32)
        proj.build()
        # simulate 50 chunk embeddings
        fake_chunks = torch.randn(1, 50, 768)
        output = proj.forward(fake_chunks)
        assert output.shape == (1, 32, 4096)

    def test_training_estimate(self):
        from poor_cli.neural_code_encoder import CodebaseProjection
        proj = CodebaseProjection()
        est = proj.training_estimate()
        assert "trainable_parameters" in est
        assert "gpu_requirement" in est
        assert "min_dataset_size" in est


class TestEmbeddingProviderIntegration:
    """Test that HF provider integrates with get_embedding_provider()."""

    def test_hf_preferred_selection(self):
        from poor_cli.embeddings import get_embedding_provider
        # if torch is available, requesting hf: prefix should return HF provider
        try:
            import torch
            import transformers
            p = get_embedding_provider("hf:codebert")
            assert p is not None
            assert p.name == "hf:codebert"
        except ImportError:
            pytest.skip("torch/transformers not installed")

    def test_fallback_still_works(self):
        from poor_cli.embeddings import get_embedding_provider
        # without preference, should still return something (or None if no provider)
        p = get_embedding_provider()
        # just verify it doesn't crash
        assert p is None or hasattr(p, "embed")
