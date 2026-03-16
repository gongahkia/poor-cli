# `poor-cli` Strategy Audit and Competitive Benchmark

As of March 16, 2026. This memo uses the current local worktree as the authoritative view of `poor-cli`, not the last release tag.

## Executive Summary

`poor-cli` currently exists to serve a specific user: a budget-conscious, terminal-native developer who wants an agentic coding workflow without committing to a single vendor, a single editor, or a hosted subscription product. In practice, it is a BYOK coding agent built around a Rust TUI, a Python execution core, a Neovim bridge, explicit approval/checkpoint flows, and unusual collaboration features such as LAN/tunnel multiplayer.

The core product is stronger than the name suggests. The current worktree already supports:

- a TUI-first interactive shell with slash-command UX and model switching
- a Python JSON-RPC server shared by the TUI and Neovim
- repo-local safety controls, trusted-root enforcement, checkpoints, audit trails, and plan review concepts
- a second, less marketed surface for headless execution, durable tasks, scheduled automations, skills, custom commands, and GitHub-triggered task creation

The strategic problem is not lack of ambition. It is coherence. Against Claude Code, OpenAI Codex, Gemini CLI, Aider, and Goose, `poor-cli` reads as an interesting hybrid of coding agent, local automation runner, and collaboration tool. That creates real upside, but today it also creates product-story blur, install friction, and maturity asymmetry across surfaces.

My bottom line:

- `poor-cli` is best positioned as an open, hackable, low-cost alternative to premium terminal agents.
- Its strongest differentiators are multiplayer collaboration, Neovim support, BYOK/local-model flexibility, and explicit repo-local governance.
- Its biggest near-term weaknesses are distribution, product clarity, operational trust, and security/runtime hardening.

## 1. Product Thesis: What `poor-cli` Is Actually For

### Core identity

The repo itself is clear that the primary product is a TUI-first coding agent, not a general-purpose Python SDK. The architecture doc describes three user-facing surfaces sharing one execution engine: the Rust TUI, the Python JSON-RPC server, and the Neovim integration, with the canonical path `TUI/Neovim -> JSON-RPC server -> PoorCLICore -> provider + tools` (`docs/architecture.md:5-20`).

The practical positioning is:

- terminal-first, with the Rust TUI as the primary surface (`docs/architecture.md:177-182`)
- BYOK and multi-provider, including Gemini, OpenAI, Anthropic, and local Ollama (`README.md:171-180`)
- collaboration-aware, with LAN/tunnel multiplayer, room roles, invite tokens, and join flows (`README.md:100-156`)
- governance-aware, with permission prompts, sandbox presets, trusted-root enforcement, checkpoints, audit logs, and plan review infrastructure (`docs/architecture.md:107-157`, `poor_cli/sandbox.py:18-223`)
- editor-adjacent, with a real Neovim plugin rather than a simple transport adapter (`nvim-poor-cli/README.md:6-19`, `nvim-poor-cli/README.md:158-186`)

That combination makes `poor-cli` closest in spirit to "open-source terminal agent shell for serious coding work" rather than "another chat wrapper for LLM APIs."

### What is primary vs. secondary

The current worktree has one primary surface and several secondary ones:

- Primary: Rust TUI for interactive coding sessions. The package metadata says the interactive client is now Rust and Python remains backend/server components (`poor_cli/__init__.py:1-9`, `poor-cli-tui/Cargo.toml:1-10`).
- Secondary but strategic: Neovim bridge with inline completion, chat, guarded execution review, and remote multiplayer attach (`nvim-poor-cli/README.md:8-19`, `nvim-poor-cli/README.md:158-186`).
- Secondary and under-marketed: headless `exec`, durable `task`, scheduled `automation`, repo/user `skills`, custom `commands`, and `github-task` creation (`poor_cli/__main__.py:92-271`, `poor_cli/__main__.py:302-756`).

The product thesis is strongest when those secondary surfaces are framed as "local autonomy and reuse around the same guarded coding engine," not as independent mini-products.

### Where the product starts to sprawl

The worktree now contains a real background-task subsystem with isolated worktrees, artifacts, and durable status (`poor_cli/task_manager.py:1-224`). It also contains a real scheduled automation subsystem backed by the task runner (`poor_cli/automation_manager.py:1-247`). Those are not fake stubs. They materially broaden `poor-cli` from an interactive agent into a local automation runtime.

That is strategically interesting, but today it also creates product-story blur because the README still overwhelmingly sells the TUI, Neovim, multiplayer, and slash commands, while the Python CLI exposes a much wider surface than the public narrative suggests (`README.md:27-180`, `poor_cli/__main__.py:302-756`).

## 2. Current-State Audit of `poor-cli`

### Shipped and user-visible today

These capabilities are clearly implemented and intentionally surfaced:

- Rust TUI interaction with provider/model overrides and remote multiplayer flags (`README.md:48-67`; verified locally with `python3 -m poor_cli --help`, which built and printed `poor-cli-tui` help)
- Python server entrypoint `poor-cli-server` as a supported integration/runtime boundary (`README.md:69-74`, `pyproject.toml:56-59`)
- model/provider support for Gemini, OpenAI, Anthropic, and Ollama (`README.md:171-180`)
- Neovim plugin with inline completion, chat, diagnostics, plan review, and remote multiplayer bridge (`nvim-poor-cli/README.md:8-19`, `nvim-poor-cli/README.md:133-186`)
- collaboration hosting and joining via WebSocket rooms with viewer/prompter roles (`README.md:100-156`)
- explicit tool capability metadata and capability-based sandbox presets (`poor_cli/tools_async.py:65-110`, `poor_cli/sandbox.py:18-223`)
- slash-command breadth through the shared command manifest (`README.md:186-240` and the generated manifest behind it)

This is not a toy repo. The product already spans local interaction, editor integration, and collaborative sessions.

### Implemented but under-marketed

The hidden story in the current worktree is the Python CLI surface:

- `poor-cli exec`: headless execution with JSON or streaming JSON output, tool allow/deny lists, context file selection, and plan-only mode (`poor_cli/__main__.py:92-271`)
- `poor-cli task`: durable local tasks with approval gates, isolated worktrees, artifacts, logs, and worker processes (`poor_cli/__main__.py:302-450`, `poor_cli/task_manager.py:43-224`)
- `poor-cli automation`: local scheduled automations on interval/daily/weekly schedules (`poor_cli/__main__.py:525-690`, `poor_cli/automation_manager.py:43-247`)
- `poor-cli skills` and `poor-cli commands`: repo-local and user-global reusable prompt wrappers (`poor_cli/__main__.py:453-523`, `poor_cli/skills.py:12-130`)
- `poor-cli github-task`: task creation from GitHub event payloads (`poor_cli/__main__.py:693-756`)

These are real features, not placeholders. The targeted CLI uplift tests for automations and GitHub task creation pass in the current worktree (`tests/test_cli_uplift.py:38-111`).

Strategically, this means `poor-cli` already has the beginnings of a local "coding agent + autonomy + reuse" platform. The problem is that the public story has not caught up.

### Documented but still aspirational

The architecture document uses several phrases that signal direction rather than fully productized reality:

- "All mutating execution is intended to pass through one guarded path" (`docs/architecture.md:107-123`)
- "The intended phase-1 plan loop is" (`docs/architecture.md:144-157`)
- "The TUI should expose backend state that materially changes execution" (`docs/architecture.md:53-60`)
- "Any user-visible command or toggle should correspond to a real backend behavior" (`docs/architecture.md:177-182`)

That wording matters. It suggests the repo has a clear target architecture, but some of the strongest safety and consistency claims are still framed as design constraints or phase-1 intent, not fully closed product guarantees.

### Packaging and install reality

This is the clearest mismatch between product ambition and current UX:

- the Python package exports `poor-cli` and `poor-cli-server` (`pyproject.toml:56-59`)
- but the interactive `poor-cli` command defers to a Rust binary and errors if it cannot find a repo-local launcher or preinstalled `poor-cli-tui` (`poor_cli/__main__.py:52-89`)
- the README explicitly says interactive `poor-cli` still requires either a repo checkout launcher or a separately installed TUI binary (`README.md:166-169`)

That is materially weaker than the one-command install stories offered by the leading tools in this category.

### Provider posture

Although the README presents symmetric multi-provider support, the Python package is not actually symmetric at install time:

- `google-genai` is a base dependency (`pyproject.toml:30-37`)
- OpenAI and Anthropic SDKs are optional extras (`pyproject.toml:39-45`)

That implies a practical bias toward Gemini as the default out-of-the-box path, which is sensible for cost and openness, but it should be treated as an intentional product choice rather than accidental symmetry.

### Local verification run for this audit

I verified the current worktree with these non-mutating checks:

- `cargo test -q` in `poor-cli-tui`: passed
- `python3 -m pytest tests/test_command_manifest.py tests/test_cli_uplift.py tests/test_skills_and_commands.py tests/test_task_manager.py tests/test_automation_manager.py -q`: 11 tests passed
- `python3 -m poor_cli exec --help`: worked
- `python3 -m poor_cli task --help`, `automation --help`, `skills --help`: all worked
- `python3 -m poor_cli --help`: built and displayed the Rust TUI help

The positive read is that the TUI and uplifted Python surfaces are not vapor. The negative read is that the same pytest run reported very low measured coverage in key Python subsystems, especially `poor_cli/_server.py`, `poor_cli/core.py`, and `poor_cli/tools_async.py`, which weakens operational trust for the most critical layers.

## 3. Competitive Comparison

### Compact comparison table

| Tool | Product posture | Install/distribution | Model/auth posture | Safety/runtime posture | Automation/headless | Extensibility | Collaboration/editor story | Where `poor-cli` is stronger | Where `poor-cli` is weaker |
|---|---|---|---|---|---|---|---|---|---|
| Claude Code | premium first-party coding agent | polished single-vendor install and docs | Anthropic-native | mature permissions, hooks, settings, subagents | strong local + GitHub Actions story | hooks, MCP, settings, subagents | IDE integrations plus CLI | BYOK, local models, multiplayer, Neovim | polish, integration depth, managed trust |
| OpenAI Codex | CLI plus broader coding platform | strong CLI + app/cloud ecosystem | OpenAI-native | approvals, sandboxing, MCP, multi-agent docs | strongest cloud/task/workflow story | AGENTS, MCP, skills, non-interactive flows | CLI, IDE, cloud | provider openness, multiplayer | platform breadth, automation maturity, overall polish |
| Gemini CLI | open-source terminal agent | easiest open install, npm/npx and strong docs | Google account/API key or Vertex | trusted folders, approval modes, checkpointing | strong non-interactive story | extensions, MCP, prompt packages | terminal-first, IDE-adjacent | Neovim plugin, multiplayer | distribution, documentation, ecosystem maturity |
| Aider | git-centric terminal pair programmer | simple terminal install/use | model-agnostic | lighter governance story, strong git workflow | strong scripting/use-in-loop pattern | config and workflow modes | editor-neutral terminal loop | collaboration, explicit approvals/checkpoints, Neovim | git-native maturity and single-user edit loop |
| Goose | local agent platform, broader than coding | multi-surface install | multi-provider | permissions and local-platform posture | recipe/platform oriented | extensions and Goosehints | desktop + CLI ecosystem | code-specific governance, multiplayer, Neovim | ecosystem packaging and general-agent platform maturity |

### Claude Code

Anthropic's docs position Claude Code as a polished first-party coding agent with quickstart onboarding, hierarchical settings, hooks, subagents, IDE integrations, and GitHub Actions support. In other words, Claude Code is not just a terminal shell; it is a deeply integrated product line across local development and team workflows.

Against Claude Code, `poor-cli` is weaker on:

- overall polish and install path
- premium trust signals and production hardening
- depth of official docs and workflow coverage
- integrated IDE and cloud-adjacent workflows

`poor-cli` is stronger or at least more distinct on:

- provider openness and BYOK flexibility
- local-model support through Ollama
- LAN/tunnel multiplayer collaboration
- a first-party Neovim bridge rather than mostly general IDE support
- explicit repo-local checkpoints and audit-oriented product language

Strategically, Claude Code is the benchmark for quality and maturity, not the best target for feature parity. `poor-cli` should not try to out-Claude Claude Code. It should beat it on openness, cost structure, editor culture, and hackability.

Sources: [Quickstart](https://docs.anthropic.com/en/docs/claude-code/quickstart), [Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents), [Settings](https://docs.anthropic.com/en/docs/claude-code/settings), [Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks), [IDE integrations](https://docs.anthropic.com/en/docs/claude-code/ide-integrations), [GitHub Actions](https://code.claude.com/docs/en/github-actions)

### OpenAI Codex

OpenAI Codex now spans more than a local CLI. The official materials position it as a software engineering agent across the terminal, IDE integrations, non-interactive runs, approvals/sandboxing, MCP, multi-agent workflows, and GitHub Actions, with the broader Codex product also covering cloud and task-oriented experiences.

Against Codex, `poor-cli` is weaker on:

- platform breadth
- non-interactive and automation maturity
- managed workflow story
- documentation density around enterprise-grade agent operations

`poor-cli` is stronger or more distinct on:

- true multi-provider posture instead of vendor lock-in
- explicit support for local models
- room-based multiplayer
- repo-local durability without depending on a hosted platform

This is the most important strategic contrast in the market. Codex is moving toward a full software-engineering platform. `poor-cli` should not chase that breadth directly. Its better lane is "local-first, open runtime for developers who want control."

Sources: [Introducing Codex](https://openai.com/index/introducing-codex/), [Codex CLI getting started](https://help.openai.com/en/articles/11096431-openai-codex-cli-getting-started), [Codex CLI](https://developers.openai.com/codex/cli), [Approvals](https://developers.openai.com/codex/approvals), [Multi-agents](https://developers.openai.com/codex/multi-agents), [Non-interactive mode](https://developers.openai.com/codex/cli/non-interactive), [GitHub Actions](https://developers.openai.com/codex/cli/github-actions), [MCP](https://developers.openai.com/codex/mcp), [OpenAI Codex repo](https://github.com/openai/codex)

### Gemini CLI

Gemini CLI is the closest open-source benchmark. Like `poor-cli`, it is terminal-first, open, and extensible. Google's official materials emphasize easy installation, multiple authentication paths, configuration, trusted folders, approval modes, checkpointing, extensions, MCP support, prompt packaging, and GitHub Actions.

Compared with Gemini CLI:

- Gemini CLI looks more mature on packaging and onboarding.
- Gemini CLI has a cleaner docs story around safety, trusted folders, checkpointing, extensions, and headless automation.
- `poor-cli` is more differentiated on collaboration and Neovim.

This is the competitor `poor-cli` should study most closely. Gemini CLI validates that there is a real market for an open, terminal-native agent shell. It also shows the bar for documentation, packaging, and extension ergonomics that `poor-cli` needs to meet.

Sources: [Gemini CLI repo](https://github.com/google-gemini/gemini-cli), [Get started](https://google-gemini.github.io/gemini-cli/docs/get-started/), [CLI docs](https://google-gemini.github.io/gemini-cli/docs/cli/), [Configuration](https://google-gemini.github.io/gemini-cli/docs/cli/configuration.html), [Trusted folders](https://google-gemini.github.io/gemini-cli/docs/cli/trusted-folders.html), [Checkpointing](https://google-gemini.github.io/gemini-cli/docs/cli/checkpointing.html), [Extensions](https://google-gemini.github.io/gemini-cli/docs/extensions/index.html)

### Aider

Aider remains the strongest "single-user, git-centric terminal coding partner" in the open toolset. Its docs emphasize working in your terminal, repository-aware editing, workflow modes such as Architect, and watch-oriented loops. Aider is narrower than `poor-cli`, but that narrowness is a strength: it has a clear product identity.

Compared with Aider:

- Aider is clearer and more mature for fast, single-user code-edit loops.
- `poor-cli` is broader, with a richer shell, Neovim bridge, explicit approval/checkpoint surfaces, and multiplayer.
- Aider still feels more focused; `poor-cli` feels more like an early platform.

This is an important warning sign. If `poor-cli` keeps expanding without clarifying its thesis, users who want "just help me patch code in git" will continue to prefer Aider's simplicity.

Sources: [Aider docs](https://aider.chat/docs/), [Modes](https://aider.chat/docs/usage/modes.html), [Watch](https://aider.chat/docs/usage/watch.html), [Config](https://aider.chat/docs/config/aider_conf.html)

### Goose

Goose is a different kind of overlap: less purely "coding agent" and more "local agent platform" across desktop and CLI surfaces, with extension mechanisms and `goosehints` for steering behavior. That makes it relevant because it competes for the same user who wants local control and extensibility.

Compared with Goose:

- Goose has a broader general-agent platform feel.
- `poor-cli` is more code-specific and repo-governance-specific.
- Goose looks stronger on packaged ecosystem thinking; `poor-cli` looks stronger on code workflow details such as checkpoints, plan review, and pair collaboration.

If `poor-cli` leans further into coding-specific governance and collaboration, it can stay differentiated. If it drifts toward a generic local agent platform, Goose becomes a more direct threat.

Sources: [Goose docs](https://block.github.io/goose/docs/), [Quickstart](https://block.github.io/goose/docs/quickstart/), [Installation](https://block.github.io/goose/docs/getting-started/installation/), [Permission modes](https://block.github.io/goose/docs/guides/goose-permissions/), [Using extensions](https://block.github.io/goose/docs/getting-started/using-extensions/), [Subagents](https://block.github.io/goose/docs/guides/subagents/), [Using goosehints](https://block.github.io/goose/docs/guides/context-engineering/using-goosehints/)

## 4. What `poor-cli` Is Currently Lacking

### Must-fix if it wants to be taken seriously against top-tier tools

1. **A frictionless install story**

The biggest product gap is still packaging. Today the Python package ships the server, but the interactive CLI depends on an external Rust binary or repo launcher (`README.md:166-169`, `poor_cli/__main__.py:77-89`). That is an immediate disadvantage against Claude Code, Codex, and Gemini CLI.

2. **A single, coherent product narrative**

The repo already contains three stories:

- TUI coding agent
- Neovim coding companion
- local automation/task runtime

All three are real. The problem is that they are not yet composed into one clear thesis. Even internals like background task branches still use a `codex/task-*` prefix (`poor_cli/task_manager.py:161-167`), which reinforces the feeling that parts of this surface are still being consolidated.

3. **Stronger runtime hardening**

`poor-cli` has good product instincts here: capability metadata, sandbox presets, approval gates, trusted roots, and safe-process mode are all real (`poor_cli/sandbox.py:18-223`, `tests/test_tools_async_capabilities.py:5-32`). But this is still application-level governance, not the stronger sandbox/runtime story users now expect from the best tools.

4. **Higher trust in core/backend layers**

For this audit, targeted tests passed, but the Python coverage output was still very low in the most critical layers. That does not mean the system is unstable, but it does mean the repo has not yet earned the same operational trust as top-tier competitors.

5. **A first-class headless/automation story**

The local worktree already has `exec`, tasks, automations, and GitHub-triggered task creation (`poor_cli/__main__.py:92-756`, `poor_cli/task_manager.py:103-224`, `poor_cli/automation_manager.py:182-247`). What it lacks is productization: clear docs, recommended flows, examples, and a narrative that explains when users should use the TUI versus headless runs versus background workers.

### Areas to double down on because they are genuinely differentiating

1. **Multiplayer collaboration**

Very few terminal agents make collaboration a first-class primitive. Room roles, join flows, and Neovim attach are genuinely distinctive (`README.md:100-156`, `README.md:158-169`, `nvim-poor-cli/README.md:162-186`).

2. **Neovim as a real surface, not a checkbox**

`poor-cli` already has a meaningful Neovim story with inline completion, chat, diagnostics, guarded execution, and multiplayer attach (`nvim-poor-cli/README.md:8-19`, `nvim-poor-cli/README.md:133-186`). That audience is worth serving deeply.

3. **Repo-local governance**

Checkpoints, audit logs, instruction stacks, policy hooks, trusted roots, and plan review are not sexy compared with model benchmarks, but they are strategically valuable for serious users (`docs/architecture.md:107-157`, `poor_cli/sandbox.py:18-223`).

4. **BYOK plus local-model flexibility**

This remains one of the cleanest reasons to pick `poor-cli` over first-party vendor tools. The repo should make that advantage more explicit.

### Gaps that matter, but can come later

- better onboarding and "which surface should I use?" documentation
- a stronger public story for skills, commands, tasks, and automations
- packaged examples and starter templates
- more visible MCP guidance and examples
- release engineering for the Rust TUI
- clearer platform support guarantees

### Deliberate non-goals that should stay non-goals

`poor-cli` should not try to match every premium platform feature from Codex or Claude Code. In particular, it does not need to become:

- a hosted vendor-controlled cloud agent platform
- a single-model, vertically integrated product
- a generic agent framework for every domain

Its best lane is narrower and stronger:

> open, local-first, terminal-native coding agent with explicit control, real collaboration, and editor-native workflows for users who value flexibility over platform lock-in

## Final Judgment

`poor-cli` already has the bones of a compelling product. The repo shows a real execution engine, a real TUI, a real Neovim bridge, a real collaboration model, and real local automation primitives. The current weakness is not "missing features" in the shallow sense. It is that the repo is ahead of the product story.

If the maintainer wants `poor-cli` to matter in this market, the next phase should not be "add even more surface area." It should be:

1. package the TUI cleanly
2. tighten the product narrative
3. harden the core runtime and tests
4. market the true differentiators: multiplayer, Neovim, BYOK/local models, and repo-local governance

Do that, and `poor-cli` stops looking like "a poor man's Claude Code" and starts looking like its own category of tool.

## Sources

### Local repo sources

- `README.md`
- `docs/architecture.md`
- `poor_cli/__main__.py`
- `poor_cli/__init__.py`
- `poor_cli/sandbox.py`
- `poor_cli/tools_async.py`
- `poor_cli/skills.py`
- `poor_cli/task_manager.py`
- `poor_cli/automation_manager.py`
- `pyproject.toml`
- `nvim-poor-cli/README.md`
- `tests/test_cli_uplift.py`
- `tests/test_tools_async_capabilities.py`

### External official sources

- Anthropic: [Claude Code quickstart](https://docs.anthropic.com/en/docs/claude-code/quickstart), [subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents), [settings](https://docs.anthropic.com/en/docs/claude-code/settings), [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks), [IDE integrations](https://docs.anthropic.com/en/docs/claude-code/ide-integrations), [GitHub Actions](https://code.claude.com/docs/en/github-actions)
- OpenAI: [Introducing Codex](https://openai.com/index/introducing-codex/), [Codex CLI getting started](https://help.openai.com/en/articles/11096431-openai-codex-cli-getting-started), [Codex CLI](https://developers.openai.com/codex/cli), [approvals](https://developers.openai.com/codex/approvals), [multi-agents](https://developers.openai.com/codex/multi-agents), [non-interactive mode](https://developers.openai.com/codex/cli/non-interactive), [GitHub Actions](https://developers.openai.com/codex/cli/github-actions), [MCP](https://developers.openai.com/codex/mcp), [openai/codex](https://github.com/openai/codex)
- Google: [Gemini CLI repo](https://github.com/google-gemini/gemini-cli), [get started](https://google-gemini.github.io/gemini-cli/docs/get-started/), [CLI docs](https://google-gemini.github.io/gemini-cli/docs/cli/), [configuration](https://google-gemini.github.io/gemini-cli/docs/cli/configuration.html), [trusted folders](https://google-gemini.github.io/gemini-cli/docs/cli/trusted-folders.html), [checkpointing](https://google-gemini.github.io/gemini-cli/docs/cli/checkpointing.html), [extensions](https://google-gemini.github.io/gemini-cli/docs/extensions/index.html)
- Aider: [docs](https://aider.chat/docs/), [modes](https://aider.chat/docs/usage/modes.html), [watch](https://aider.chat/docs/usage/watch.html), [config](https://aider.chat/docs/config/aider_conf.html)
- Goose: [docs](https://block.github.io/goose/docs/), [quickstart](https://block.github.io/goose/docs/quickstart/), [installation](https://block.github.io/goose/docs/getting-started/installation/), [permission modes](https://block.github.io/goose/docs/guides/goose-permissions/), [using extensions](https://block.github.io/goose/docs/getting-started/using-extensions/), [subagents](https://block.github.io/goose/docs/guides/subagents/), [using goosehints](https://block.github.io/goose/docs/guides/context-engineering/using-goosehints/)
