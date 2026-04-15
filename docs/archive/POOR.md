# POOR.md — poor-cli Project Rules

North-star: `median_usd_per_completion`. Audience: cost-conscious hobbyists (PRD 062).

## Architecture

- Python backend: `poor_cli/` package. Entrypoint `poor_cli.__main__:main`; server `poor_cli.server:main`.
- Neovim plugin: `nvim-poor-cli/lua/poor-cli/`. Transport: JSON-RPC over stdio.
- Provider adapters under `poor_cli/providers/` (Gemini, OpenAI, Anthropic, OpenRouter, Ollama, hf_local, vLLM, llama-server, SGLang, HF TGI, LM Studio).
- Research modules under `poor_cli/research/` gated by feature flags; top-level shims at `poor_cli/latent_communication.py` and `poor_cli/neural_code_encoder.py` are intentional deprecation shims, not stubs.

## Key Conventions

- File naming: Python package uses `poor_cli` (underscore), CLI and plugin use `poor-cli` (hyphen).
- Rules precedence (high → low): repo AGENTS.md (closest-dir-wins), repo POOR.md, repo CLAUDE.md, `~/.poor-cli/POOR.md`, `~/.poor-cli/AGENTS.md`.
- Memory (cross-session): `~/.poor-cli/memory/*.md` with YAML frontmatter; `~/.poor-cli/memory/MEMORY.md` is the index.

## Strategic Decisions (Phase 20, 2026-04-14)

- PRD 059 Latent communication: **ship, scoped to `hf_local` only** (`docs/archive/phase_20/059_outcome.md`).
- PRD 061 Project rename: **keep `poor-cli`** (`docs/archive/phase_20/061_outcome.md`).
- PRD 062 Audience + metric: **cost-conscious hobbyists + `median_usd_per_completion`** (`NORTH_STAR.md`).
- PRD 063 Multiplayer: **commit as first-class**, 2-minute demo video is gating deliverable (`docs/phase_20/063_outcome.md`).

## Workflow

1. Verify strategy before writing code.
2. `make lint && make test` before landing changes. Lua suite: `make test-lua` (requires plenary).
3. Research modules must stay feature-flag gated; never unconditionally import from `poor_cli.research.*`.
4. Do NOT auto-refactor outside the immediate scope of the task.
5. In-line comments only (lowercase default; Capitalize tech names).
