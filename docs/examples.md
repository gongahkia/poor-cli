# Examples

## Small Direct Task

```sh
poor-cli run "fix the typo in README" --yes
poor-cli replay <run_id> --verify
```

Expected artifacts: `PLAN.md`, `tasks/*/RESULT.md`, `review/REVIEW.json`, `verify/VERIFY.json`.

## Fusion-reviewed Task

```toml
[routes.reviewer]
profile = "openrouter"
model = "openrouter/fusion"
fusion = true
max_cost_usd = 1.00
analysis_models = ["~google/gemini-flash-latest", "~moonshotai/kimi-latest"]
judge_model = "~anthropic/claude-opus-latest"
```

```sh
poor-cli review-run <run_id> --allow-expensive-router
```

Expected artifacts: `review/FUSION.json` and `review/REVIEW.json`.

## Kimi Executor Swarm

```sh
poor-cli provider add kimi --model kimi-k2.7-code
poor-cli route set --role executor --profile kimi --model kimi-k2.7-code
poor-cli run-swarm "split the independent docs fixes" --parallel 2 --allow-dirty
```

Expected artifacts: worker worktree metadata, patch collection, and `merge/MERGE_PLAN.json`.

## Local Graph Run

```sh
POOR_CLI_PROVIDER=vllm POOR_CLI_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct \
  poor-cli run "trace parser flow" --graph --yes
```

Expected artifacts: `graph.context`, context packets, provider/tool replay artifacts.

## Web Research

```sh
poor-cli run "answer the provider API question with citations" --yes
```

Expected artifacts: `web.search`, `web.fetch`, `web.cache`, and `web.citation` when web tools are used.

## Prompt-pack Review

```sh
poor-cli prompt packs
poor-cli review-run <run_id>
```

Expected behavior: reviewer prompt includes assumption checks, contrary evidence, missing tests, security risk, and benchmark-gated claim checks.
