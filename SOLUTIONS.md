# Token Optimization Solutions for Agentic Coding Systems

A comprehensive catalog of optimization strategies, ranked by **feasibility of implementation** — accounting for engineering effort, dependencies (closed vs. open-weights models), maturity of reference implementations, and how much custom work is needed.

Feasibility scoring rubric:
- 🟢 **Easy** — Drop-in middleware, well-documented libraries, weeks of work
- 🟡 **Moderate** — Custom integration but proven techniques, months of work
- 🟠 **Hard** — Requires inference-layer access, model-specific tuning, or significant infra
- 🔴 **Research-grade** — Requires open-weights models, training, or unproven territory

---

## 🟢 Easy / High-ROI Solutions

### 1. Prompt Caching (Provider-Level)
**What it solves:** Static prompt redundancy, system prompt bloat (partial)

Anthropic's prompt caching reduces costs by up to 90% and latency by up to 85% for long prompts. Cache reads cost $0.30/M tokens vs $3.00/M fresh processing. OpenAI achieves 50% cost reduction with automatic caching enabled by default.

**Limitations:** Short prompts below the 1,024-token threshold won't benefit. Heavy personalization breaks the prefix.

**Reference:** [Anthropic Prompt Caching docs](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)

---

### 2. Diff-Based Editing Formats
**What it solves:** Edit format tax, output token waste

The "diff" edit format asks the LLM to specify file edits as a series of search/replace blocks, returning only changed parts. **Patch generation with EASE reduces token usage by 31%** while maintaining edit quality within 5% of full regeneration. OpenAI's `apply_patch` format avoids line numbers and uses distinct delimiters.

**Reference:**
- [Aider edit formats documentation](https://aider.chat/docs/more/edit-formats.html)
- [EASE paper](https://arxiv.org/abs/2407.04816) — patch generation with 31% token reduction
- OpenAI `apply_patch` format (used in Codex CLI)

---

### 3. Schema-Aware Tool Output Filtering
**What it solves:** Tool/MCP response bloat

Have the agent declare what fields it wants in the tool call (JSONPath, JMESPath, GraphQL-style), and filter the response server-side before it reaches context. Pure middleware engineering — no model changes needed. Could also be done with a tiny "extractor" LLM as a sidecar.

**Why easy:** Standard data engineering, well-understood libraries.

**Reference:** No standard implementation exists yet — this is a gap, not a solved problem. Closest analog: GraphQL field selection patterns.

---

### 4. Aider-Style Repo Map (Tree-Sitter + PageRank)
**What it solves:** Codebase reading inefficiency

Aider sends a concise map of the whole git repository including the most important classes/functions and their signatures. Built using **tree-sitter** to parse source into ASTs, then **PageRank-scored** on a graph where files are nodes and edges are dependencies. The key insight: a function called by 20 other functions is more valuable context than a private helper called once.

**Reference:**
- [Aider repo map docs](https://aider.chat/docs/repomap.html)
- [Aider GitHub](https://github.com/Aider-AI/aider)
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/)

---

### 5. Manual Context Compaction (`/compact` style)
**What it solves:** Context window accumulation

Replace the conversation input with a smaller representative summary once tokens exceed a threshold. Already shipped in Claude Code as `/compact`, GPT-5.2-Codex includes context compaction for long-horizon work.

**Reference:**
- [Claude Code `/compact` command](https://docs.claude.com/en/docs/agents-and-tools/claude-code/overview)
- Anthropic engineering blog on context management

---

### 6. Semantic Caching for Agent Outputs (GPTCache / MeanCache)
**What it solves:** Duplicate query re-inference

Compare semantic similarity of queries via embeddings rather than literal text matching. **GPTCache** is production-ready with 6,000+ GitHub stars. **GPT Semantic Cache** reduces API calls by up to 68.8% with 97% precision on hits. **MeanCache** uses federated learning for privacy-preserving per-user caches, outperforming GPTCache by 17% F-score.

**Reference:**
- [GPTCache GitHub](https://github.com/zilliztech/GPTCache) — production-ready, LangChain/LlamaIndex integrated
- [GPT Semantic Cache paper (arXiv:2411.05276)](https://arxiv.org/abs/2411.05276)
- [MeanCache paper (arXiv:2403.02694)](https://arxiv.org/abs/2403.02694)

---

### 7. Grammar-Constrained Decoding
**What it solves:** Output token waste, malformed-output retry loops

Use grammar constraints (GBNF, Outlines, XGrammar) so the model can only emit valid tokens for the schema. No malformed JSON, no retry loops, often 30–50% shorter outputs because the model can't ramble.

**Reference:**
- [Outlines](https://github.com/dottxt-ai/outlines) — structured generation library
- [XGrammar](https://github.com/mlc-ai/xgrammar) — fast grammar-constrained decoding
- [llama.cpp GBNF docs](https://github.com/ggerganov/llama.cpp/blob/master/grammars/README.md)

---

### 23. CLI Output Proxy / Filter (RTK — Rust Token Killer)
**What it solves:** Ambient noise pollution (#9), tool/MCP output bloat (#2, shell-mediated), codebase reading inefficiency (#3, for `cat`/`grep`/`ls` paths)

A single-binary CLI proxy that intercepts shell commands before they execute and rewrites their output into a token-compact form before it reaches the agent's context. Works via a **PreToolUse hook** that transparently rewrites `git status` → `rtk git status`, `cat file.rs` → `rtk read file.rs`, `cargo test` → `rtk test cargo test`, etc. — the agent never sees the rewrite, just receives filtered output. Four strategies per command type: smart filtering (strips boilerplate/whitespace/banners), grouping (aggregates files by directory, errors by rule), truncation (keeps relevant context, cuts redundancy), and deduplication (collapses repeated log lines with counts). Reported savings: **60–90% on common dev commands** — e.g. `git push` from ~200 tokens to ~10, `cargo test` from 200+ lines to ~20 on failure, `ls -la` from ~800 tokens to ~150. A tee mode optionally persists raw output on failure so the agent can recover full detail without re-executing. Ships with 100+ supported commands covering git, gh, cargo, npm/pnpm, pytest, ruff, docker, kubectl, aws, curl, and more.

**Why easy:** Production-ready drop-in middleware. Install via `brew install rtk` + `rtk init -g`, restart the agent, done. Zero model changes, zero prompt rewriting, zero infra. Works with Claude Code, Cursor, Gemini CLI, Codex, Windsurf, Cline, OpenCode out of the box via their respective hook APIs.

**Rough integration idea for poor CLI:** Two plausible paths. (a) *Wrap it*: shell out to the existing `rtk` binary from poor CLI's tool-execution layer — poor CLI registers a pre-execute middleware that, for any bash tool call matching rtk's supported command set, prefixes `rtk ` before spawning the subprocess. Zero reimplementation cost, inherits all 100+ command handlers and future updates for free, just a dependency on the user having rtk installed (or we bundle it). (b) *Port it*: rewrite the filter pipeline natively inside poor CLI as a Rust module (or Python if poor CLI is Python), lifting rtk's per-command parsers (git porcelain parser, cargo test JSON parser, eslint formatter, etc.) into poor CLI's own tool-output post-processing stage. More work but removes the external binary dependency and lets poor CLI apply the same filters to non-shell tool outputs (e.g. MCP responses, file reads via the native `Read` tool which rtk's hook currently can't intercept). Recommendation: start with (a) as a one-week integration, measure real savings on poor CLI sessions, then selectively port the highest-ROI filters (git, cargo/npm test, grep, cat) into native code to cover the `Read`/`Grep`/`Glob` built-ins that bypass bash hooks.

**Reference:**
- [RTK GitHub](https://github.com/rtk-ai/rtk) — 19.5k stars, Apache-2.0, single Rust binary
- [RTK website](https://www.rtk-ai.app)
- [RTK architecture docs](https://github.com/rtk-ai/rtk/blob/master/docs/contributing/ARCHITECTURE.md)

---

## 🟡 Moderate Solutions

### 8. Progressive Skill Loading (CLAUDE.md → Skills Architecture)
**What it solves:** CLAUDE.md / system prompt bloat

Break monolithic CLAUDE.md into a skills directory loaded on demand based on task relevance. **ClaudeFast's Code Kit** uses progressive disclosure across 20+ skills to recover roughly 15,000 tokens per session — an 82% improvement. Anthropic's official Skills system formalizes this pattern.

**Reference:**
- [Anthropic Skills documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
- ClaudeFast Code Kit (search "ClaudeFast" on GitHub)

---

### 9. LLM Cascading / Routing (FrugalGPT, RouteLLM)
**What it solves:** Wrong-sized model for task, overall cost

Route each query through progressively-larger models, stopping when a confidence-scoring function says the cheap one's answer is good enough. **FrugalGPT matches GPT-4 performance with up to 98% cost reduction** on some datasets. **RouteLLM** trains a router on preference data for one-shot routing, achieving 2× cost savings without quality loss.

**Reference:**
- [FrugalGPT paper (arXiv:2305.05176)](https://arxiv.org/abs/2305.05176)
- [RouteLLM paper (arXiv:2406.18665)](https://arxiv.org/abs/2406.18665)
- [RouteLLM GitHub](https://github.com/lm-sys/RouteLLM)
- [Unified Routing & Cascading (arXiv 2025)](https://files.sri.inf.ethz.ch/website/papers/dekoninck2024cascaderouting.pdf)

---

### 10. LLMLingua Prompt Compression
**What it solves:** System prompt bloat, tool output bloat, codebase reading inefficiency

Use a small model (GPT-2 small or LLaMA-7B) to compute per-token perplexity and delete redundant tokens before sending to the big model. **Up to 20× compression with ~1.5% accuracy loss on GSM8K**. **LongLLMLingua** boosts RAG performance by 21.4% using only 1/4 the tokens via query-aware compression. **LLMLingua-2** is a BERT-sized classifier, 3–6× faster.

**Why moderate:** Drop-in middleware, but tuning compression ratios per content type takes work.

**Reference:**
- [LLMLingua GitHub](https://github.com/microsoft/LLMLingua) — Microsoft Research, integrated with LangChain/LlamaIndex
- [LLMLingua paper (arXiv:2310.05736)](https://arxiv.org/abs/2310.05736)
- [LLMLingua-2 paper (arXiv:2403.12968)](https://arxiv.org/abs/2403.12968)
- [LongLLMLingua](https://arxiv.org/abs/2310.06839)

---

### 11. AST-Aware Code Chunking for RAG
**What it solves:** Codebase reading inefficiency, naive chunking failures

Traditional character/line-based chunking breaks code structure. AST-based chunking preserves syntactic validity. LLMs can be used to generate natural language descriptions for each code chunk, embedded alongside the code to improve natural language query retrieval.

**Reference:**
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
- [LlamaIndex code splitter](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/code/)
- [CodeRAG-Bench](https://arxiv.org/abs/2406.14497) — eval framework for code RAG

---

### 12. Importance-Weighted History Pruning
**What it solves:** Context window accumulation

Score each turn for importance using a small model and prune the bottom N% rather than blanket-summarizing. **H2O** does this at the KV-cache level for individual tokens (the "heavy hitter oracle"). For agent conversations, you'd score *turns* — early planning turns matter, failed tool calls from 20 turns ago can probably be dropped entirely.

**Reference:**
- [H2O paper (NeurIPS 2023)](https://arxiv.org/abs/2306.14048)
- [Scissorhands paper](https://arxiv.org/abs/2305.17118) — persistence of importance hypothesis
- [Letta / MemGPT](https://github.com/letta-ai/letta) — closest existing memory hierarchy implementation

---

### 13. Speculative Decoding with Draft Models
**What it solves:** Cost per token (especially for predictable code)

Pair a small draft model (0.5B) with the main model. The draft proposes K tokens, the main verifies them in one forward pass. **Up to 3× faster LLM inference**. For coding agents specifically, acceptance rates are very high because so many tokens are syntactically determined (closing braces, type annotations, imports). **EAGLE-3** uses prediction heads attached to the target model's internals, eliminating the need for a separate draft model.

**Why moderate:** Requires inference-layer access (vLLM, SGLang). Not usable with closed APIs.

**Reference:**
- [vLLM speculative decoding docs](https://docs.vllm.ai/en/latest/features/spec_decode/)
- [EAGLE-3 GitHub](https://github.com/SafeAILab/EAGLE)
- [Medusa](https://github.com/FasterDecoding/Medusa)
- [Speculative Sampling (DeepMind)](https://arxiv.org/abs/2302.01318)

---

### 14. Lazy Tool Schema Loading
**What it solves:** Verbose tool schemas in system prompt

Train a small classifier that maps "current task description" → "minimal tool set needed," loaded just-in-time. Skills can be hierarchically organized so loading "Python testing" automatically pulls in "Python basics." Essentially a package manager for tool schemas.

**Why moderate:** No off-the-shelf solution. Custom build, but the techniques (small classifiers, dynamic prompts) are well understood.

**Reference:** No reference implementation — gap in the ecosystem. Closest analog: dynamic MCP server selection in some agent frameworks.

---

## 🟠 Hard Solutions (Significant Infrastructure Required)

### 15. Position-Independent KV Cache Reuse (CacheBlend / EPIC)
**What it solves:** Position encoding waste, codebase reading inefficiency

Standard prompt caching only works on **prefix** matches. CacheBlend reuses precomputed KV caches **regardless of position**, selectively recomputing only 5–18% of tokens to maintain quality. **2.2–3.3× TTFT reduction** without quality loss. **EPIC** formalizes Position-Independent Caching (PIC) — like dynamically linked libraries for attention states. Pre-compute KV cache of every file in the repo, store on disk, assemble per-query.

**Why hard:** Requires deep integration with inference engine (vLLM). Not usable with closed APIs.

**Reference:**
- [CacheBlend paper (EuroSys 2025 best paper)](https://arxiv.org/abs/2405.16444)
- [LMCache GitHub](https://github.com/LMCache/LMCache) — open-source implementation
- [EPIC paper (arXiv:2410.15332)](https://arxiv.org/abs/2410.15332)
- [Prompt Cache paper](https://arxiv.org/abs/2311.04934) — pioneered the approach

---

### 16. Selective Failure Amnesia
**What it solves:** Retry / failure tax

After a failed tool call, extract only the lesson learned ("file path was wrong, correct location is X") and prune the full failure trace from context. Requires a meta-controller that decides what to keep vs. discard.

**Why hard:** Requires careful reasoning about what context the agent will need later. No standard implementation exists.

**Reference:** No reference implementation. Closest research: episodic memory in agent systems, [Reflexion paper (arXiv:2303.11366)](https://arxiv.org/abs/2303.11366).

---

### 17. Reinforcement Learning for Token Budget Allocation
**What it solves:** Wrong-sized resources for task, overall cost

Train a meta-controller that learns when to spend tokens vs. be terse. Observes (task difficulty, current context size, tools available) and outputs (max thinking tokens, tool call budget, model choice). Essentially learns the FrugalGPT routing policy end-to-end.

**Reference:**
- [Learning how hard to think (arXiv:2410.04707)](https://arxiv.org/abs/2410.04707) — input-adaptive LM computation allocation
- [Confident Adaptive Language Modeling (DeepMind)](https://arxiv.org/abs/2207.07061)

---

### 18. Differential Context Updates (Structured Deltas)
**What it solves:** Context window accumulation, codebase reading inefficiency

Between turns, the agent doesn't re-read the full conversation. Instead, it receives a *diff* of what changed since its last snapshot — new files, modified files (as patches), new user message. The agent maintains its own working memory across turns. Closest existing work: **Letta (formerly MemGPT)**, which gives the agent an OS-style memory hierarchy.

**Reference:**
- [Letta GitHub](https://github.com/letta-ai/letta) — OS-style memory for agents
- [MemGPT paper (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560)

---

## 🔴 Research-Grade Solutions (Open-Weights Required, Unproven)

### 19. Latent-Space Inter-Agent Communication (LatentMAS / Interlat)
**What it solves:** Multi-agent coordination overhead

Instead of subagents communicating via text messages, they pass each other their **last-layer hidden states directly**. The receiving agent prepends those states into its KV cache and continues reasoning. No round-tripping through tokens.

- **LatentMAS** (Princeton/UIUC/Stanford, Nov 2025): training-free, **70.8–83.7% output token reduction, 4–4.3× faster inference**, AND up to 14.6% accuracy gains.
- **Interlat**: compresses multi-agent messages to as few as **8 latent tokens** vs. full CoT plans. **24× speedup**.

**Why research-grade:** Requires open-weights models you control inference for. Won't work with closed APIs (Claude, GPT). But this is also the *moat* — nobody using closed APIs can compete.

**Reference:**
- [LatentMAS GitHub](https://github.com/Gen-Verse/LatentMAS)
- [LatentMAS paper (arXiv:2511.20639)](https://arxiv.org/abs/2511.20639)
- [Interlat paper (arXiv:2511.09149)](https://arxiv.org/abs/2511.09149)

---

### 20. Latent Reasoning (Coconut / CODI / Quiet-STaR)
**What it solves:** CoT verbosity, reasoning token overhead

Same trick applied to a single model's chain-of-thought: the model loops its hidden state back as input instead of decoding to text. Hidden states carry ~40k bits each vs. ~15 bits per text token, so per-"thought" bandwidth is dramatically higher. Could collapse 2000-token CoT traces to a few dozen latent states.

**Reference:**
- [Coconut paper (Meta, arXiv:2412.06769)](https://arxiv.org/abs/2412.06769)
- [Quiet-STaR paper (arXiv:2403.09629)](https://arxiv.org/abs/2403.09629)
- [CODI paper](https://arxiv.org/abs/2502.21074)

---

### 21. Code-Specific Tokenizers
**What it solves:** Code tokenization inefficiency

BPE tokenizers were trained on natural language and fragment identifiers/syntax inefficiently. Train a tokenizer specifically on code corpora, or use AST-token hybrid representations where syntactic structure is encoded out-of-band.

**Why research-grade:** Requires retraining the model OR running a full conversion layer. No production deployment of this approach exists.

**Reference:**
- [CodeBPE](https://arxiv.org/abs/2308.00683) — code-aware tokenization research
- [AST-T5](https://arxiv.org/abs/2401.03003) — structure-aware pretraining

---

### 22. Neural Code Embeddings as Context Substitute
**What it solves:** Codebase reading inefficiency (radical version)

Instead of putting code in context at all, fine-tune the model with a vision-style "code encoder" that ingests embedded representations of the codebase as a side input. The agent gets a `<codebase>` token that expands into learned embeddings in cross-attention layers. Treat the codebase like an image (CLIP/LLaVA pattern).

**Why research-grade:** Pure speculation. Would require model training. But the architectural pattern works for vision so the analogy is plausible.

**Reference:** No reference implementation. Closest analog: [LLaVA (vision-language model)](https://arxiv.org/abs/2304.08485) for the architectural pattern. [CodeBERT](https://arxiv.org/abs/2002.08155) for code embeddings.

---

## Summary Table

| # | Solution | Feasibility | Best For | Reference Status |
|---|---|---|---|---|
| 1 | Provider-level prompt caching | 🟢 Easy | Static prompt redundancy | Production (Anthropic/OpenAI) |
| 2 | Diff-based editing formats | 🟢 Easy | Edit format tax | Production (Aider, Codex) |
| 3 | Schema-aware tool filtering | 🟢 Easy | Tool output bloat | **Gap — no standard impl** |
| 4 | Tree-sitter repo maps | 🟢 Easy | Codebase reading | Production (Aider) |
| 5 | Manual `/compact` | 🟢 Easy | Context accumulation | Production (Claude Code) |
| 6 | Semantic caching (GPTCache) | 🟢 Easy | Duplicate queries | Production-ready library |
| 7 | Grammar-constrained decoding | 🟢 Easy | Output verbosity | Production (Outlines) |
| 8 | Progressive skill loading | 🟡 Moderate | CLAUDE.md bloat | Anthropic Skills, ClaudeFast |
| 9 | LLM cascading (FrugalGPT) | 🟡 Moderate | Cost optimization | Research → production |
| 10 | LLMLingua compression | 🟡 Moderate | Prompt/output bloat | Microsoft Research, integrated |
| 11 | AST-aware code chunking | 🟡 Moderate | RAG over code | LlamaIndex impl |
| 12 | Importance-weighted history | 🟡 Moderate | Context accumulation | H2O, Scissorhands research |
| 13 | Speculative decoding | 🟡 Moderate | Per-token cost | vLLM, SGLang production |
| 14 | Lazy tool schema loading | 🟡 Moderate | Tool schema bloat | **Gap — no standard impl** |
| 15 | Position-independent KV reuse | 🟠 Hard | Repeated context | LMCache (open-source) |
| 16 | Selective failure amnesia | 🟠 Hard | Retry tax | **Gap — no standard impl** |
| 17 | RL token budget allocation | 🟠 Hard | Adaptive cost | Research only |
| 18 | Differential context updates | 🟠 Hard | Context accumulation | Letta/MemGPT (closest) |
| 19 | Latent-space agent comm | 🔴 Research | Multi-agent overhead | LatentMAS GitHub (Nov 2025) |
| 20 | Latent reasoning (Coconut) | 🔴 Research | CoT verbosity | Meta research |
| 21 | Code-specific tokenizers | 🔴 Research | Tokenization waste | CodeBPE, AST-T5 research |
| 22 | Neural code embeddings | 🔴 Research | Codebase reading | Pure speculation |
| 23 | CLI output proxy (RTK) | 🟢 Easy | Ambient noise, shell tool bloat | **Production (rtk-ai/rtk, 19.5k ★)** |

---

## Key Gaps in the Ecosystem (Greenfield Opportunities)

Solutions marked **"Gap — no standard impl"** are particularly interesting for a research project because they represent real, painful problems with no good off-the-shelf fix:

1. **Schema-aware tool output filtering** — pure middleware engineering, immediate impact
2. **Lazy tool schema loading** — small classifier + dynamic prompt assembly
3. **Selective failure amnesia** — meta-controller deciding what to remember from failures

These three together would likely deliver 30–50% token savings on real coding sessions and could be built without touching model internals or requiring open-weights models.

---

## Addendum: Solution #24 — Caveman Output-Style Skill

### 24. Caveman-Speak Output Compression Skill
**What it solves:** Markdown formatting overhead (#18), CoT verbosity on visible output (#14, partial)

**Feasibility:** 🟢 Easy (trivially so — it's a single skill file)

**Reference:** [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — MIT-licensed Claude Code skill, installable via `claude install-skill JuliusBrussee/caveman`.

**What it is (and is not):** A Claude Code *skill* — a behavioral prompt that Claude loads on trigger (`/caveman`, "caveman mode", "less tokens please") and obeys until told to stop. It is **not** a proxy, middleware, meta-prompt layer, or interception shim sitting above Claude Code. It runs *inside* Claude Code the same way any other skill does. Functionally it is a single thing: a directive to output responses in a telegraphic "caveman-speak" register — no articles (a/an/the), no pleasantries ("Sure, I'd be happy to…"), no hedging ("it might be worth considering…"), no filler connectors — while preserving code blocks, technical terminology (polymorphism stays polymorphism), error messages (quoted exactly), and git commits/PR descriptions in normal prose. Example from the README: "The reason your React component is re-rendering is likely because you're creating a new object reference on each render cycle…" (69 tokens) compresses to "New object ref each render. Inline object prop = new ref = re-render. Wrap in `useMemo`." (19 tokens). Claimed ~75% output reduction with 100% technical accuracy retention.

**Evaluation of usefulness as a solution:** Narrow and bounded, but real within its lane. Honest assessment:

- **Scope is output-only.** Caveman compresses the tokens Claude *generates*, not the tokens Claude *reads*. In agentic coding sessions, input (context history, tool results, code reads, MCP schemas, CLAUDE.md) typically dominates total spend at roughly 85–95% of tokens; output is 5–15%. A 75% cut on the smaller slice yields maybe 4–11% total session savings in realistic workloads — non-zero but far from transformative.
- **Targets only low-severity pain.** Maps to 🟢 Low pain point #18 (markdown/verbose output, ~10–20% output overhead) with marginal spillover into 🟡 Medium #14 (CoT verbosity, and only for *visible* output — extended thinking/hidden reasoning tokens are untouched). It does **nothing** for any 🔴 Critical pain point (#1–#5 context accumulation, tool bloat, codebase reads, CLAUDE.md bloat, retry tax) or 🟠 High pain point (#6 tool schemas, #9 ambient noise, #10 edit format tax, #11 multi-agent overhead).
- **No compounding.** Unlike prompt caching (#1) or RTK (#23), caveman's savings don't stack into the next turn — every turn re-pays the same accumulated input context regardless of how terse the previous answer was. It reduces the *new* output added per turn but not the quadratic input growth that drives long-session cost.
- **Fragile at the prompt level.** Any turn where Claude judges normal prose necessary (detailed explanations, onboarding a user, writing docs, writing commits/PRs — explicitly carved out by the skill itself) silently reverts to full verbosity. There is no enforcement layer.
- **What it does get right.** Zero integration cost (one-line install), zero infra, no model changes, MIT-licensed, stackable with every other solution in this document without conflict. As a free addition on top of a real stack (prompt caching + repo maps + RTK + diff-based edits), it's a reasonable marginal win with negative engineering overhead.

**Recommendation:** Worth installing as a cheap supplementary tweak for cost-sensitive long sessions, but it should not be counted as addressing any of the Critical or High pain points and should not displace engineering effort on solutions #1–#8 or #23. Rank it *below* every other 🟢 Easy solution in priority order: it's the smallest lever in the box, even though it's also the easiest to pull.

---

## Updated Summary Table Entry

| # | Solution | Feasibility | Best For | Reference Status |
|---|---|---|---|---|
| 24 | Caveman output-style skill | 🟢 Easy | Markdown/prose output verbosity (#18) | Production skill (JuliusBrussee/caveman, MIT) |

**Priority note:** Among 🟢 Easy solutions, Caveman is the lowest-impact entry. Typical ordering by realistic session savings: #1 Prompt caching → #5 `/compact` → #23 RTK → #4 Repo maps → #2 Diff edits → #6 Semantic caching → #3 Schema-aware tool filtering → #7 Grammar-constrained decoding → **#24 Caveman**.
