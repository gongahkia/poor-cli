# PRD 022: Wire repo-graph PageRank into file selection

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (1.5w)
- **Blocked by:** 018
- **Files it mutates:**
  - `poor_cli/repo_graph.py` (narrow — expose a `pagerank_score(path) -> float` API)
  - `poor_cli/context_assembly.py` (use scores in selection)
  - `poor_cli/context_engine.py`
- **New files it adds:**
  - `tests/test_pagerank_selection.py`

## 1. Problem

`poor_cli/repo_graph.py` is ~1,717 lines, builds a dependency graph, and computes PageRank — but those scores never reach file selection. Leaf files and hub files are weighted the same. LEARNING.md §2.1, §2.2: "Integrate repo-graph PageRank into file selection. Better context quality."

Aider's core innovation is exactly this (see Aider docs on repo map). We have the ingredients; we haven't wired them.

## 2. Current state

- `repo_graph.py` has PageRank computed and persisted in `.poor-cli/repo_graph.db`.
- `context_engine.py` / `context.py` select files by recency + import-aware traversal.
- No cross-module query from selection to PageRank.

## 3. Goal & non-goals

**Goal:** file selection weighs candidates by a combined score: `alpha * recency + beta * pagerank + gamma * import_distance`. Defaults tuned so the change is a net quality improvement on a benchmark (Aider-style).

**Non-goals:**
- Do not re-implement PageRank.
- Do not add a new graph source.
- Do not change the schema of `repo_graph.db`.

## 4. Design

### 4.1 Public API on repo_graph

```python
# poor_cli/repo_graph.py (add)
def pagerank_score(self, path: str | Path) -> float:
    """Return PageRank in [0, 1] for path. 0 if not indexed."""
def top_k(self, k: int = 50) -> list[tuple[str, float]]:
    """Top-k files by PageRank."""
```

### 4.2 Selection change in `context_assembly`

```python
SCORE_WEIGHTS = {"recency": 0.4, "pagerank": 0.4, "import_distance": 0.2}

def score(candidate: FileCandidate) -> float:
    r = recency_score(candidate)             # 0..1
    pr = repo_graph.pagerank_score(candidate.path)  # 0..1
    d  = import_distance_score(candidate)    # 0..1
    return (SCORE_WEIGHTS["recency"] * r
          + SCORE_WEIGHTS["pagerank"] * pr
          + SCORE_WEIGHTS["import_distance"] * d)
```

### 4.3 Config

`context.selection_weights` overridable in `preferences.json`.

### 4.4 Cold-start behavior

On first run, PageRank may not be computed yet (`_ensure_repo_graph` is async). If unavailable within 100 ms, fall back to weights `{"recency": 0.6, "pagerank": 0, "import_distance": 0.4}` so the wait doesn't stall turns.

## 5. Files to create / modify / delete

**Create**
- `tests/test_pagerank_selection.py`

**Modify**
- `poor_cli/repo_graph.py` — expose API.
- `poor_cli/context_assembly.py` — consume API.
- `poor_cli/context_engine.py` — integrate scoring.

## 6. Implementation plan

1. Add `pagerank_score` + `top_k` to repo_graph with unit tests.
2. Integrate into assembly scoring.
3. Config option; cold-start fallback.
4. Benchmark: pick a small open repo, compare context picks before/after with a handful of canned prompts; include in PR description.
5. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_top_k_returns_sorted`
- `test_assembly_prefers_pagerank_hubs_over_leaves`
- `test_cold_start_fallback_when_graph_missing`

**Done criterion**
- [ ] PageRank influences selection.
- [ ] Benchmark shows hub files surface earlier.
- [ ] Cold-start is not blocked.

## 8. Rollback / risk

Low. Weights configurable; set `pagerank=0` to disable.

## 9. Out-of-scope & boundary

- 🚫 Do not change repo_graph's indexer internals.
- 🚫 Do not add visual output (PRD 038 covers that).

## 10. Related PRDs & references

- PRD 018, 038.
- Aider repo map docs.
- LEARNING.md §2.1.
