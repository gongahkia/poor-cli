# Token Burn Pain Points in Agentic Coding Systems

A comprehensive taxonomy of where tokens get burned in agentic coding harnesses (Claude Code, Codex CLI, Aider, Cursor, etc.), ranked by **how painful each is for end users** — accounting for frequency, magnitude, and how often users actually run into the wall.

Pain scoring rubric:
- 🔴 **Critical** — Users hit this constantly, blocks long sessions, dominates cost
- 🟠 **High** — Frequent and expensive, causes visible session degradation
- 🟡 **Medium** — Real problem but workarounds exist or impact is bounded
- 🟢 **Low** — Niche or rarely user-visible

---

## 🔴 Critical Pain Points

### 1. Context Window Accumulation (The Primary Killer)
Claude Code is stateless — it re-processes the entire conversation history with each new message to maintain context. Conversation history accumulates with each turn, and agent loops compound the problem. An agent that takes 10 steps to complete a task might consume 10× the tokens of a single-shot approach. Long, unmanaged sessions lead to high token counts AND degraded performance because of attention dilution. This is the #1 cost driver and the #1 reason users hit `/clear` mid-task.

**Why it's #1:** Every other pain point compounds through this one. Every wasted token becomes a permanent tax on every subsequent turn until the session is cleared.

---

### 2. Tool Output / MCP Response Bloat
APIs were built for traditional software, not LLM context windows. A single MCP call to fetch a user profile can return 40KB of JSON timestamps, nested metadata, tracking IDs, and null fields when the agent only needed ~120 bytes. The entire payload gets dumped into context. A single MCP call can consume 5% of a 200K-token window. Multiple calls accelerate context overflow rapidly. Users hit this without realizing — they see "agent ran out of context" without understanding that one tool call ate 10K tokens of timestamps.

---

### 3. Codebase Reading Inefficiency
When you ask the agent to "look at the codebase and figure out X," it reads several files in sequence, each adding full content to context. A `grep` across a large repo, a `cat` of a 500-line file, or a failed shell command with a long stack trace — all of it accumulates. Worse, code tokenizes inefficiently at 1.5–2.0 tokens per word vs. 0.7 for natural language, so codebase reads are doubly expensive.

---

### 4. CLAUDE.md / System Prompt Bloat
Your `CLAUDE.md` gets injected into EVERY single request. Every turn. Every follow-up. Every `/clear` and fresh start. A 5,000-token CLAUDE.md taxes you 5,000 tokens before the model even reads your code. For a "fix typo in README" task, ~2,100 tokens may be loaded but only ~300 (14%) are actually relevant. Database schemas, deployment configs, testing guides, and architecture diagrams all load even when the task has nothing to do with them.

---

### 5. The Retry / Failure Tax
When an agent fails — wrong file edit, broken test, hallucinated API — it doesn't just lose those tokens. It now has to read the failure into context, reason about why, and retry. A single tool failure can compound into 3–10× the tokens of a successful execution because the failure trace, error stack, and reasoning all stay in context permanently. No agent currently does "amnesia on failure" — selectively forgetting failed attempts after extracting the lesson. Users feel this as "why is my session suddenly so slow and expensive after that one bug?"

---

## 🟠 High Pain Points

### 6. Verbose Tool Schemas in System Prompt
MCP servers and tool definitions get injected as JSON Schema into every turn. A typical session with 5–10 MCP servers can carry **8–15K tokens of tool schemas** before the user types anything. Most of those tools are never called in a given session. There's almost no work being done on lazy/on-demand tool schema loading — agents pay the full menu cost for every meal.

---

### 7. "Lost in the Middle" Phenomenon
LLMs drop 30%+ accuracy when key information sits in the middle of context. Liu et al. (2024) proved the U-shaped attention curve. Chroma's 2025 study tested 18 frontier models including Claude Opus 4 — all showed degradation. Reasoning performance starts degrading around ~3,000 tokens, well below stated context windows. Users pay for the tokens AND get worse output. Even chain-of-thought prompting doesn't fix it.

---

### 8. Extended Thinking / Reasoning Token Overhead
Extended thinking reserves up to 31,999 output tokens per request for internal reasoning. A large portion of generated CoT serves linguistic coherence rather than task-relevant information. Subagents (Task tool) compound this — each subagent does its own model and tool work, consuming more tokens than comparable single-agent runs. Users often don't realize how much they're paying for "thinking" they never see.

---

### 9. Context Pollution from Ambient Noise
Git status, file trees, terminal banners, deprecation warnings, stderr noise from tools, npm install output, build warnings — none of which the user asked for, all of which the agent has to read and ignore. This is the dark matter of token usage: invisible but everywhere. It's high pain because users can't even see it happening.

---

### 10. The Edit Format Tax
The same edit can take 3× more tokens depending on the format used (full file rewrite vs. unified diff vs. search/replace blocks vs. apply_patch). Worse: weaker models silently fall back to rewriting whole files when they fail at structured diffs, doubling cost invisibly. Users see "the model edited my file" without realizing it just rewrote 800 lines to change 2.

---

### 11. Multi-Agent Coordination Overhead
When you spawn subagents (Claude Code Task tool, AutoGen, CrewAI), every agent-to-agent message round-trips through *text*. Agent A's hidden state → text → Agent B reads text → Agent B's hidden state. That round-tripping is enormously lossy AND expensive. Recent research suggests this accounts for 70–80% of multi-agent token spend.

---

## 🟡 Medium Pain Points

### 12. Code Tokenization Inefficiency
BPE tokenizers were trained on natural language corpora, so they fragment identifiers, indentation, and syntax inefficiently. `getUserAccountByID` might be 5+ tokens when semantically it's one symbol. Code tokenizes at 1.5–2.0 tokens per word vs. 0.7 for English. This is medium because it's a constant tax rather than a spike, and users have no agency to fix it.

---

### 13. Duplicate / Near-Duplicate Queries Within Sessions
Devs ask the same question phrased slightly differently across sessions, or even within one session ("explain this function" → later "what does X do" referring to the same function). Almost no coding agent does semantic caching at the response level. Production query streams show 60%+ duplicate rates.

---

### 14. Chain-of-Thought Verbosity
Beyond extended thinking — even normal CoT outputs are bloated. A large portion of generated text serves to maintain linguistic coherence rather than convey essential information. Users pay output token costs for filler.

---

### 15. Position Encoding Waste in Repeated Contexts
Standard prompt caching only works on **prefix** matches. If the same file appears in your context but not at the start (e.g., you re-read it after some other tool calls), you re-pay full prefill. Most agents don't exploit non-prefix cache reuse.

---

### 16. Static Prompt Redundancy Across Sessions
Even with prompt caching at the provider level, short prompts below the 1,024-token threshold won't benefit. Teams that personalize system prompts heavily undermine prefix caching entirely. The cache helps but is brittle.

---

## 🟢 Low Pain Points (Real but bounded or niche)

### 17. Tokenizer Mismatch for Special Characters
Unicode-heavy content, emoji in commit messages, non-ASCII identifiers. Real but rare in coding contexts.

---

### 18. Wasted Output Tokens on Markdown Formatting
Agents tend to produce verbose markdown (headers, bullet lists, bold) even for short answers. Adds 10–20% output overhead but bounded.

---

### 19. Failed Cache Invalidation
When the system prompt or tool list changes mid-session, cache gets invalidated and you re-pay full prefill. Annoying but infrequent.

---

## Summary Table

| # | Pain Point | Severity | Avg Token Impact |
|---|---|---|---|
| 1 | Context window accumulation | 🔴 Critical | O(n²) growth |
| 2 | Tool/MCP output bloat | 🔴 Critical | 5–50K per call |
| 3 | Codebase reading inefficiency | 🔴 Critical | Scales with repo |
| 4 | CLAUDE.md / system prompt bloat | 🔴 Critical | 2–10K per turn |
| 5 | Retry / failure tax | 🔴 Critical | 3–10× wasted |
| 6 | Verbose tool schemas | 🟠 High | 8–15K per session |
| 7 | Lost-in-the-middle degradation | 🟠 High | 30%+ accuracy drop |
| 8 | Extended thinking overhead | 🟠 High | Up to 32K hidden |
| 9 | Ambient noise pollution | 🟠 High | 1–5K per tool call |
| 10 | Edit format tax | 🟠 High | Up to 3× per edit |
| 11 | Multi-agent text round-trips | 🟠 High | 70–80% of MA tokens |
| 12 | Code tokenization inefficiency | 🟡 Medium | 1.5–2× constant tax |
| 13 | Duplicate query re-inference | 🟡 Medium | Full re-cost per dup |
| 14 | CoT verbosity | 🟡 Medium | Variable |
| 15 | Non-prefix cache misses | 🟡 Medium | Full re-prefill |
| 16 | Static prompt redundancy | 🟡 Medium | Bounded by caching |
| 17 | Tokenizer special-char issues | 🟢 Low | Rare |
| 18 | Markdown formatting overhead | 🟢 Low | 10–20% output |
| 19 | Cache invalidation events | 🟢 Low | Infrequent |
