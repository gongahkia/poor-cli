"""
Neural code embeddings for poor-cli.

Provides HuggingFace-based code embedding (CodeBERT, UniXcoder, CodeSage)
as an EmbeddingProvider, plus a NeuralCodeRetriever that uses embedding
similarity to select top-K relevant chunks for LLM context — replacing
brute-force "stuff everything in context" with neural retrieval.

Architecture study: LLaVA/CLIP → code analogy
----------------------------------------------
LLaVA pattern: Image → CLIP ViT → Linear Projection → LLM input tokens
Code analog:   Codebase → Code Encoder → Projection → LLM input tokens

Key finding: LLaVA does NOT use cross-attention — it projects visual tokens
directly into the LLM's input sequence via a simple linear layer. The code
analog would project code embeddings into pseudo-tokens that the LLM treats
as regular input. However:

1. Scale mismatch: ViT produces 256-576 tokens for one image. A codebase
   needs thousands of chunks encoded — token budget explodes without
   aggressive compression (perceiver/cross-attention bottleneck).
2. Granularity: CLIP encodes one image holistically. Codebases are
   multi-entity (files, functions, deps). No existing code encoder
   handles repo-level in one pass.
3. Training: requires (codebase, question, answer) triples and fine-tuning
   a projection layer. SWE-bench could provide data but this is a
   research-level effort.
4. No published work exists (as of early 2025) demonstrating end-to-end
   "codebase as embedding" analogous to LLaVA.

PRACTICAL ALTERNATIVE (this module): neural retrieval.
Embed chunks via CodeBERT/UniXcoder, retrieve top-K by cosine similarity,
include only relevant chunks in context. This is the proven production
pattern (Cursor, Aider, Continue.dev all use it).
"""

from __future__ import annotations
import asyncio
import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from .embeddings import EmbeddingProvider, cosine_similarity, rank_by_similarity
from .exceptions import setup_logger

logger = setup_logger(__name__)

# supported HuggingFace code embedding models
HF_CODE_MODELS = {
    "codebert": "microsoft/codebert-base",        # 768d, 512 tok max
    "unixcoder": "microsoft/unixcoder-base",       # 768d, 512 tok max, contrastive-pretrained
    "graphcodebert": "microsoft/graphcodebert-base", # 768d, 512 tok max, data-flow aware
    "codesage-small": "codesage/codesage-small",   # 1024d, 2048 tok max
}
DEFAULT_HF_MODEL = "unixcoder" # best retrieval quality out of the box


class HuggingFaceCodeEmbedding(EmbeddingProvider):
    """Local code embedding via HuggingFace transformers.

    Uses CodeBERT/UniXcoder/GraphCodeBERT for code-aware embeddings.
    Runs entirely local — no API keys, no network, no cost.
    Requires: pip install transformers torch
    """

    def __init__(self, model_key: str = DEFAULT_HF_MODEL, device: str = "auto", batch_size: int = 32):
        self._model_key = model_key
        self._model_name = HF_CODE_MODELS.get(model_key, model_key) # allow raw HF model name
        self._device = device
        self._batch_size = batch_size
        self._model = None
        self._tokenizer = None
        self._dims: Optional[int] = None

    @property
    def name(self) -> str:
        return f"hf:{self._model_key}"

    @property
    def dimensions(self) -> int:
        if self._dims is not None:
            return self._dims
        return 768 # default for BERT-base family

    def available(self) -> bool:
        try:
            import torch # noqa: F401
            import transformers # noqa: F401
            return True
        except ImportError:
            return False

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        self._model = AutoModel.from_pretrained(self._model_name)
        if self._device == "auto":
            self._device = "mps" if torch.backends.mps.is_available() else (
                "cuda" if torch.cuda.is_available() else "cpu"
            )
        self._model = self._model.to(self._device)
        self._model.eval()
        self._dims = self._model.config.hidden_size
        logger.info("loaded %s on %s (%dd)", self._model_name, self._device, self._dims)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using mean pooling over last hidden states."""
        import torch
        self._load_model()
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            # truncate long inputs (CodeBERT max 512 tokens)
            encoded = self._tokenizer(
                batch, padding=True, truncation=True,
                max_length=512, return_tensors="pt",
            ).to(self._device)
            with torch.no_grad():
                outputs = self._model(**encoded)
            # mean pool over non-padding tokens
            hidden = outputs.last_hidden_state # (batch, seq, dim)
            mask = encoded["attention_mask"].unsqueeze(-1).float() # (batch, seq, 1)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            # L2 normalize for cosine similarity
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            for vec in pooled.cpu().numpy():
                all_embeddings.append(vec.tolist())
        return all_embeddings

    def embed_sync(self, texts: List[str]) -> List[List[float]]:
        """Synchronous embedding for benchmark/CLI use."""
        return asyncio.run(self.embed(texts))


# ── neural retrieval pipeline ───────────────────────────────────────────

@dataclass
class RetrievalResult:
    """A chunk retrieved by neural similarity."""
    file_path: str
    chunk_content: str
    similarity: float
    chunk_name: str = ""
    node_type: str = ""
    start_line: int = 0
    end_line: int = 0

    def context_block(self) -> str:
        """Format as a context block for LLM prompt injection."""
        header = f"## {self.file_path}"
        if self.chunk_name:
            header += f" :: {self.chunk_name}"
        if self.start_line:
            header += f" (L{self.start_line}-{self.end_line})"
        header += f"  [sim={self.similarity:.3f}]"
        return f"{header}\n```\n{self.chunk_content}\n```"


class NeuralCodeRetriever:
    """Retrieve top-K relevant code chunks by embedding similarity.

    Enhancement over Phase 5B's AST chunking: instead of heuristic file
    selection, use learned code embeddings to rank chunks by semantic
    relevance to the user's query.

    Integration: plugs into CodebaseIndexer's existing embedding storage.
    Can also operate standalone with its own in-memory index.
    """

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        model_key: str = DEFAULT_HF_MODEL,
        device: str = "auto",
    ):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.embedder = HuggingFaceCodeEmbedding(model_key=model_key, device=device)
        self._chunk_store: List[Dict[str, Any]] = [] # in-memory chunk index
        self._embeddings: List[List[float]] = [] # parallel array of embeddings
        self._indexed = False

    async def index_codebase(
        self,
        indexer: Any = None, # CodebaseIndexer instance
        progress_callback: Any = None,
    ) -> Dict[str, Any]:
        """Index codebase chunks using HF embeddings.

        If a CodebaseIndexer is provided, reads chunks from its SQLite DB
        and stores HF embeddings alongside existing API embeddings.
        Otherwise, indexes directly from filesystem.
        """
        if indexer is not None:
            return await self._index_from_indexer(indexer, progress_callback)
        return await self._index_from_filesystem(progress_callback)

    async def _index_from_indexer(self, indexer: Any, progress_callback: Any) -> Dict[str, Any]:
        """Read chunks from CodebaseIndexer's DB, compute HF embeddings."""
        import sqlite3
        conn = indexer._connect()
        try:
            rows = conn.execute("""
                SELECT c.chunk_id, c.file_path, c.chunk_index, c.content,
                       c.node_type, c.name, c.start_line, c.end_line, c.description
                FROM chunks c
            """).fetchall()
        finally:
            conn.close()
        if not rows:
            return {"error": "no chunks in index — run 'index' first", "indexed": 0}
        self._chunk_store = [dict(r) for r in rows]
        texts = [r["content"][:2000] for r in rows] # truncate for encoder
        t0 = time.time()
        self._embeddings = await self.embedder.embed(texts)
        elapsed = time.time() - t0
        self._indexed = True
        if progress_callback:
            progress_callback(f"hf-embedded {len(self._embeddings)} chunks in {elapsed:.1f}s")
        logger.info("neural index: %d chunks in %.1fs via %s", len(self._embeddings), elapsed, self.embedder.name)
        return {
            "provider": self.embedder.name,
            "indexed": len(self._embeddings),
            "elapsed_seconds": round(elapsed, 2),
        }

    async def _index_from_filesystem(self, progress_callback: Any) -> Dict[str, Any]:
        """Index directly from filesystem (standalone mode, no CodebaseIndexer)."""
        from .indexer import CodebaseIndexer
        idx = CodebaseIndexer(self.repo_root)
        idx.index() # build AST chunks
        return await self._index_from_indexer(idx, progress_callback)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.1,
        file_filter: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """Retrieve top-K chunks most relevant to query by cosine similarity."""
        if not self._indexed or not self._embeddings:
            logger.warning("neural index not built — call index_codebase() first")
            return []
        query_vecs = await self.embedder.embed([query])
        if not query_vecs or not query_vecs[0]:
            return []
        query_vec = query_vecs[0]
        scored: List[Tuple[int, float]] = []
        for i, emb in enumerate(self._embeddings):
            if not emb:
                continue
            if file_filter:
                fp = self._chunk_store[i].get("file_path", "")
                if file_filter not in fp:
                    continue
            sim = cosine_similarity(query_vec, emb)
            if sim >= min_similarity:
                scored.append((i, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, sim in scored[:top_k]:
            chunk = self._chunk_store[idx]
            results.append(RetrievalResult(
                file_path=chunk.get("file_path", ""),
                chunk_content=chunk.get("content", ""),
                similarity=round(sim, 4),
                chunk_name=chunk.get("name", ""),
                node_type=chunk.get("node_type", ""),
                start_line=chunk.get("start_line", 0),
                end_line=chunk.get("end_line", 0),
            ))
        return results

    async def retrieve_context(
        self,
        query: str,
        max_tokens: int = 4000,
        top_k: int = 20,
        min_similarity: float = 0.15,
    ) -> str:
        """Retrieve and format relevant chunks as a context string for LLM prompt.

        Token-aware: stops adding chunks when budget is exhausted.
        """
        results = await self.retrieve(query, top_k=top_k, min_similarity=min_similarity)
        blocks = []
        token_est = 0
        for r in results:
            block = r.context_block()
            chunk_tokens = len(block) // 4 # rough estimate: 4 chars per token
            if token_est + chunk_tokens > max_tokens:
                break
            blocks.append(block)
            token_est += chunk_tokens
        if not blocks:
            return ""
        return "# Neural Retrieval Context\n\n" + "\n\n".join(blocks)


# ── LLaVA-style projection research prototype ──────────────────────────

class CodebaseProjection:
    """RESEARCH PROTOTYPE: LLaVA-style projection from code embeddings to LLM space.

    This is the speculative "full neural embedding" approach. NOT functional
    without training. Documented here for architecture reference.

    Architecture:
        Code chunks → CodeBERT/UniXcoder (768d per chunk)
        → Attention pooling (N chunks → K summary vectors)
        → Linear projection (768d → LLM hidden dim, e.g. 4096d)
        → K pseudo-tokens injected into LLM input sequence

    Training requirements:
        - Dataset: (codebase_chunks, question, answer) triples
          Source: SWE-bench (~2.3K instances), or synthetic from docstrings
        - Freeze: code encoder + LLM weights
        - Train: attention pooling + projection layer only
        - GPU: ~1x A100 (40GB) for 7B LLM, ~4x for 13B
        - Time: ~1-2 days for projection-only training
        - Data: minimum ~10K triples for reasonable alignment

    Why this likely isn't worth pursuing (yet):
        1. Retrieval achieves ~80-90% of the quality with zero training
        2. Projection requires per-LLM training (not portable)
        3. Fixed-size representation loses fine-grained code detail
        4. No existing code encoder handles repo-level semantics
    """

    def __init__(self, code_dim: int = 768, llm_dim: int = 4096, num_tokens: int = 32):
        self.code_dim = code_dim
        self.llm_dim = llm_dim
        self.num_tokens = num_tokens
        self._projection = None
        self._attention_pool = None

    def build(self) -> None:
        """Build projection layers (requires torch)."""
        import torch
        import torch.nn as nn
        # attention pooling: N chunk embeddings → K summary vectors
        self._attention_pool = nn.MultiheadAttention(
            embed_dim=self.code_dim,
            num_heads=8,
            batch_first=True,
        )
        # learned query vectors for cross-attention pooling
        self._queries = nn.Parameter(torch.randn(1, self.num_tokens, self.code_dim))
        # projection: code_dim → llm_dim
        self._projection = nn.Sequential(
            nn.Linear(self.code_dim, self.llm_dim),
            nn.GELU(),
            nn.Linear(self.llm_dim, self.llm_dim),
        )
        logger.info(
            "projection built: %d code_dim → %d tokens × %d llm_dim",
            self.code_dim, self.num_tokens, self.llm_dim,
        )

    def forward(self, chunk_embeddings: Any) -> Any:
        """Project N chunk embeddings → K pseudo-tokens in LLM space.

        Args:
            chunk_embeddings: (1, N, code_dim) tensor of chunk embeddings

        Returns:
            (1, num_tokens, llm_dim) tensor of pseudo-tokens for LLM injection
        """
        import torch
        if self._projection is None:
            raise RuntimeError("call build() first")
        # cross-attention pool: queries attend to chunk embeddings
        queries = self._queries.expand(chunk_embeddings.size(0), -1, -1)
        pooled, _ = self._attention_pool(queries, chunk_embeddings, chunk_embeddings)
        # project to LLM space
        return self._projection(pooled)

    def parameter_count(self) -> int:
        """Total trainable parameters."""
        import torch
        if self._projection is None:
            return 0
        total = sum(p.numel() for p in self._projection.parameters())
        total += sum(p.numel() for p in self._attention_pool.parameters())
        total += self._queries.numel()
        return total

    def training_estimate(self) -> Dict[str, Any]:
        """Estimate training requirements."""
        params = self.parameter_count() if self._projection else (
            self.code_dim * self.llm_dim * 2 + # projection
            self.code_dim * self.code_dim * 4 + # attention
            self.num_tokens * self.code_dim # queries
        )
        return {
            "trainable_parameters": params,
            "frozen_parameters": "code encoder (~125M) + LLM (7B-13B)",
            "min_dataset_size": "~10K (codebase, question, answer) triples",
            "dataset_sources": ["SWE-bench (~2.3K)", "synthetic from docstrings", "CodeSearchNet (~6.4M pairs)"],
            "gpu_requirement": "1x A100 40GB (7B LLM) or 4x A100 (13B LLM)",
            "estimated_training_time": "1-2 days (projection only)",
            "framework": "PyTorch + HuggingFace transformers + PEFT",
        }
