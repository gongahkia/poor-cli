# PRD 060: Publish SWE-bench Lite score

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (2w)
- **Blocked by:** —
- **Files it mutates:**
  - `docs/BENCHMARKS.md` (new; or update existing)
  - `README.md`
- **New files it adds:**
  - `bench/swe_bench_lite/run.py`
  - `bench/swe_bench_lite/results/`
  - `docs/BENCHMARKS.md`

## 1. Problem

No published performance numbers. Benchmark-conscious users can't evaluate `poor-cli` vs Aider / Claude Code. LONGTERM-TODO H3, LEARNING.md §4.4.

## 2. Current state

No benchmarks.

## 3. Goal & non-goals

**Goal:** a reproducible SWE-bench Lite run (or Aider's edit benchmark — owner chooses). Publish methodology + results + cost. Single number becomes citable.

**Non-goals:**
- Do not optimize for the benchmark.
- Do not compare models (one model per run; run twice if needed).

## 4. Design

Use official SWE-bench Lite harness + `poor-cli exec --prompt $task`. Run 300-task Lite subset with one default model (e.g., Claude Sonnet). Record pass@1, cost per task, time per task.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Set up SWE-bench Lite harness.
2. Run with `poor-cli` as the agent (one model).
3. Publish results (`docs/BENCHMARKS.md`).
4. Link from README.
5. Badge with score.

## 7. Testing & acceptance criteria

- Results file checked in.
- README links to it.

**Done criterion**
- [ ] Score published with methodology.

## 8. Rollback / risk

None — adding data.

## 9. Out-of-scope & boundary

- 🚫 Do not cherry-pick tasks.
- 🚫 Do not tune for benchmark.

## 10. Related PRDs & references

- LONGTERM-TODO H3.
- LEARNING.md §4.4.
- SWE-bench: https://www.swebench.com/
