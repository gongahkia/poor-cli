# Phase 8: Research Frontier — Open-Weights & Experimental

**Priority:** Lowest (but highest potential upside) — 🔴 Research-grade solutions requiring open-weights models, custom training, or unproven techniques.
**Estimated agents:** 4 (parallel — all independent research tracks)
**Dependencies:** Phases 1–7 should be substantially complete. These solutions are long-term R&D bets, not near-term shipping targets.
**Philosophy:** The biggest moats in token optimization come from techniques that closed-API users *cannot* replicate. Every solution here requires model-level access that only open-weights provide. If poor-cli can deliver these, it creates genuine competitive advantage vs. tools locked to closed APIs.

---

## Agent 8A: Latent-Space Inter-Agent Communication

**Pain points addressed:** #11 (multi-agent text round-trips — 70–80% of multi-agent token spend)
**Solution reference:** Solution #19 from SOLUTIONS.md
**Expected savings:** 70.8–83.7% output token reduction, 4–4.3× faster inference, up to 14.6% accuracy gains

### What to build

Replace text-based communication between agents with direct hidden-state passing. Instead of Agent A writing text → Agent B reading text, Agent A passes its last-layer hidden states directly into Agent B's KV cache.

### Why this matters for poor-cli

poor-cli already has multi-agent infrastructure (`poor-cli/parallel_agents.py`, `poor-cli/agent_runner.py`). When agents coordinate (e.g., architect agent → editor agent), they currently round-trip through text — the most expensive part of multi-agent workflows. Latent communication could make poor-cli's multi-agent mode dramatically cheaper than any closed-API competitor.

### Research & implementation plan

1. **Literature review** — deep-read these papers:
   - [LatentMAS](https://arxiv.org/abs/2511.20639) — training-free approach from Princeton/UIUC/Stanford
   - [Interlat](https://arxiv.org/abs/2511.09149) — compresses to 8 latent tokens, 24× speedup
   - Document: what model architectures are supported? What inference framework is required?

2. **Feasibility assessment** — answer:
   - Which open-weights models work? (LLaMA, Mistral, Qwen?)
   - Which inference frameworks expose hidden states? (vLLM, SGLang, transformers?)
   - What's the minimum infrastructure? (GPU memory, framework version)
   - Can this work with Ollama, or does it require raw vLLM/transformers?

3. **Prototype architecture**:
   ```python
   class LatentAgent:
       """Agent that communicates via hidden states instead of text."""
       
       def __init__(self, model, role: str):
           self.model = model
           self.role = role
           self.kv_cache = None
       
       async def think(self, input_text: str, 
                       latent_context: torch.Tensor | None = None) -> tuple[str, torch.Tensor]:
           """
           Process input, optionally prepending latent context from another agent.
           Returns (text_output, hidden_states_for_next_agent).
           """
           if latent_context is not None:
               # prepend other agent's hidden states to KV cache
               self.kv_cache = prepend_latent(self.kv_cache, latent_context)
           
           output, hidden_states = self.model.generate_with_hidden(
               input_text, kv_cache=self.kv_cache
           )
           return output, hidden_states[-1]  # last layer hidden states
   
   class LatentAgentOrchestrator:
       """Coordinates agents using latent communication."""
       
       async def architect_to_editor(self, task: str):
           # architect produces plan as latent states (no text serialization)
           plan_text, plan_latent = await self.architect.think(task)
           # editor receives latent plan directly
           edit_text, _ = await self.editor.think(
               "Execute this plan:", latent_context=plan_latent
           )
           return edit_text
   ```

4. **Integration with existing agent system**:
   - `poor-cli/parallel_agents.py` — add latent communication mode
   - `poor-cli/architect_mode.py` — architect → editor via latent states
   - Gate behind feature flag + local inference detection

5. **Benchmarking**:
   - Compare text-based vs latent communication on 20 multi-agent tasks
   - Measure: tokens used, wall-clock time, task success rate
   - Document infrastructure requirements and performance trade-offs

### Files to create/modify
- `poor-cli/latent_communication.py` (new, research prototype)
- `poor-cli/parallel_agents.py` (add latent mode)
- `poor-cli/architect_mode.py` (latent architect-editor pipeline)
- `docs/LATENT_COMMUNICATION.md` (research findings and setup guide)

### Acceptance criteria
- [ ] Literature review complete with feasibility assessment
- [ ] Prototype works with at least one open-weights model (LLaMA preferred)
- [ ] Latent communication demonstrably reduces tokens vs text communication
- [ ] Performance benchmarked on multi-agent tasks
- [ ] Feature gated behind local inference + compatible model detection
- [ ] Documentation: infrastructure requirements, supported models, limitations

### References
- [LatentMAS GitHub](https://github.com/Gen-Verse/LatentMAS)
- [LatentMAS paper](https://arxiv.org/abs/2511.20639)
- [Interlat paper](https://arxiv.org/abs/2511.09149)

---

## Agent 8B: Latent Reasoning (Coconut / CODI / Quiet-STaR)

**Pain points addressed:** #8 (extended thinking overhead — up to 32K hidden tokens), #14 (CoT verbosity)
**Solution reference:** Solution #20 from SOLUTIONS.md
**Expected savings:** Could collapse 2000-token CoT traces to dozens of latent states; ~40,000 bits per hidden state vs ~15 bits per text token

### What to build

Train or fine-tune a model to perform chain-of-thought reasoning in latent space (hidden states) rather than text. The model loops its hidden state back as input instead of decoding to text, performing "thinking" without generating text tokens.

### Research & implementation plan

1. **Literature review** — deep-read:
   - [Coconut (Meta)](https://arxiv.org/abs/2412.06769) — continuous thought, training-time modification
   - [Quiet-STaR](https://arxiv.org/abs/2403.09629) — internal reasoning during generation
   - [CODI](https://arxiv.org/abs/2502.21074) — cooperative decoding for internal dialogue
   - Key question: can any of these be applied to existing open-weights models without full retraining?

2. **Feasibility triage**:
   - Coconut requires **training-time modification** — likely impractical unless fine-tuning
   - Quiet-STaR can be applied post-hoc to some models — most feasible
   - CODI requires cooperative training — impractical for off-the-shelf models

3. **Quiet-STaR prototype** (most feasible path):
   ```python
   class QuietSTaRInference:
       """Run Quiet-STaR style internal reasoning during generation."""
       
       def __init__(self, model):
           self.model = model
           # trained thought heads (would need fine-tuning)
           self.thought_start_head = ...
           self.thought_end_head = ...
       
       async def generate_with_internal_reasoning(self, prompt: str) -> str:
           """Generate response with hidden reasoning steps."""
           # at each token position, run parallel internal reasoning branch
           # reasoning branch doesn't produce text tokens
           # reasoning hidden states influence the main generation
           ...
   ```

4. **Practical alternative: thinking token budget optimization**:
   If full latent reasoning is infeasible, implement a simpler optimization:
   - Analyze how many thinking tokens the model actually uses per task type
   - Set per-task thinking token budgets based on historical data
   - For simple tasks (typo fix), set thinking budget to 0
   - For complex tasks, allow full thinking budget
   - This is the "learning how hard to think" approach from Phase 7A, applied specifically to thinking tokens

5. **Integration**:
   - Only relevant for local inference with compatible models
   - Gate behind feature flag + model compatibility check
   - Fall back to standard generation for incompatible models

### Files to create/modify
- `poor-cli/latent_reasoning.py` (new, research prototype)
- `poor-cli/thinking_budget.py` (new, practical alternative — thinking token optimization)
- `docs/LATENT_REASONING.md` (research findings)

### Acceptance criteria
- [ ] Literature review complete with feasibility ranking
- [ ] At least one approach prototyped (Quiet-STaR preferred)
- [ ] Practical alternative (thinking token budgets) implemented regardless
- [ ] Performance benchmarked vs standard CoT
- [ ] Documented: which models support this, infrastructure requirements
- [ ] Feature gated behind compatibility detection

### References
- [Coconut (Meta)](https://arxiv.org/abs/2412.06769)
- [Quiet-STaR](https://arxiv.org/abs/2403.09629)
- [CODI](https://arxiv.org/abs/2502.21074)
- [Learning how hard to think](https://arxiv.org/abs/2410.04707)

---

## Agent 8C: Code-Specific Tokenizer Research

**Pain points addressed:** #12 (code tokenization inefficiency — 1.5–2× constant tax)
**Solution reference:** Solution #21 from SOLUTIONS.md
**Expected savings:** 30-50% token reduction on code content (theoretical)

### What to build

Research and prototype tokenizers optimized for code rather than natural language. BPE tokenizers fragment identifiers, indentation, and syntax inefficiently — a code-aware tokenizer could dramatically reduce token counts for the same code.

### Research & implementation plan

1. **Quantify the problem** — measure actual tokenization overhead on poor-cli's codebase:
   ```python
   import tiktoken
   enc = tiktoken.encoding_for_model("gpt-4")
   
   for file in repo_files:
       code = file.read_text()
       tokens = enc.encode(code)
       words = len(code.split())
       ratio = len(tokens) / words  # expect 1.5-2.0 for code vs 0.7 for English
       print(f"{file}: {ratio:.2f} tokens/word")
   ```

2. **Literature review**:
   - [CodeBPE](https://arxiv.org/abs/2308.00683) — code-aware BPE
   - [AST-T5](https://arxiv.org/abs/2401.03003) — structure-aware pretraining
   - Key question: can we use a code-optimized tokenizer as a pre-processing step without retraining the model?

3. **Approach A: Code pre-tokenization** — a preprocessing step that makes code more tokenizer-friendly without changing the model:
   ```python
   def code_pretokenize(code: str) -> str:
       """Transform code to tokenize more efficiently with standard BPE."""
       # collapse indentation: 4 spaces → single indent token
       code = collapse_indentation(code)
       # merge common identifier patterns: getUserAccountByID → get_user_account_by_id
       # (snake_case tokenizes better than camelCase with most BPE)
       code = normalize_identifiers(code)
       # strip comments if the model doesn't need them
       code = strip_non_essential_comments(code)
       return code
   ```
   Caveat: this changes the code the model sees, which could affect edit accuracy.

4. **Approach B: Hybrid AST-token representation** — represent code as a mix of AST structure (compact) and token text (for identifiers):
   ```
   # instead of sending full code:
   def calculate_total(items: list[dict]) -> float:
       total = 0.0
       for item in items:
           total += item["price"] * item["quantity"]
       return total
   
   # send AST-compact:
   func calculate_total(items: list[dict]) -> float:
     var total = 0.0
     for item in items: total += item.price * item.quantity
     return total
   ```

5. **Approach C: Token vocabulary extension** — train additional BPE merges on code corpora and propose them as a tokenizer extension:
   - Requires model access and tokenizer modification
   - Only feasible for self-hosted models
   - Document findings for potential upstream contributions

6. **Benchmarking**:
   - Measure token count for 100 files with standard vs optimized tokenization
   - Measure task success rate with pre-tokenized vs original code
   - Identify the approach with best savings-to-accuracy ratio

### Files to create/modify
- `poor-cli/code_tokenizer.py` (new, research prototype)
- `docs/CODE_TOKENIZER_RESEARCH.md` (findings, benchmarks, recommendations)
- Scripts for benchmarking (in `tests/` or separate benchmark directory)

### Acceptance criteria
- [ ] Tokenization overhead quantified for poor-cli's codebase
- [ ] Literature review complete
- [ ] At least one approach prototyped and benchmarked
- [ ] Token reduction measured without quality loss
- [ ] Documented: feasible vs infeasible approaches, trade-offs
- [ ] Recommendation: which approach (if any) to pursue for production

### References
- [CodeBPE](https://arxiv.org/abs/2308.00683)
- [AST-T5](https://arxiv.org/abs/2401.03003)
- [tiktoken](https://github.com/openai/tiktoken) — for benchmarking

---

## Agent 8D: Neural Code Embeddings as Context Substitute

**Pain points addressed:** #3 (codebase reading inefficiency — the radical version)
**Solution reference:** Solution #22 from SOLUTIONS.md
**Expected savings:** Potentially orders of magnitude — entire codebase as a fixed-size embedding vector instead of thousands of text tokens

### What to build

Instead of putting code in context as text, fine-tune a model with a "code encoder" that ingests embedded representations of the codebase as a side input. The agent receives a `<codebase>` token that expands into learned embeddings via cross-attention. This treats the codebase like an image in multimodal models.

### Important caveat

This is **pure speculation** with no existing implementation. The architectural pattern works for vision (LLaVA, CLIP) so the analogy is plausible, but this would be a novel research contribution.

### Research & implementation plan

1. **Architecture study** — understand the LLaVA/CLIP pattern:
   - [LLaVA](https://arxiv.org/abs/2304.08485): vision encoder → projection layer → LLM cross-attention
   - Can we replace "vision encoder" with "code encoder"?
   - What would the code encoder look like? (CodeBERT? GraphCodeBERT? New architecture?)

2. **CodeBERT baseline** — start with an existing code encoder:
   ```python
   class CodebaseEncoder:
       """Encode entire codebase into fixed-size embedding."""
       
       def __init__(self, model_name="microsoft/codebert-base"):
           self.encoder = AutoModel.from_pretrained(model_name)
       
       def encode_codebase(self, files: list[CodeFile]) -> torch.Tensor:
           """Produce a single embedding representing the codebase."""
           file_embeddings = [self.encode_file(f) for f in files]
           # aggregate: attention-pooled combination of all file embeddings
           return self.aggregate(file_embeddings)
   ```

3. **Projection layer** — map code embeddings to the LLM's embedding space:
   ```python
   class CodeProjection(nn.Module):
       """Project code embeddings into LLM's hidden dimension."""
       
       def __init__(self, code_dim=768, llm_dim=4096, num_tokens=32):
           super().__init__()
           self.projection = nn.Linear(code_dim, llm_dim * num_tokens)
           self.num_tokens = num_tokens
       
       def forward(self, code_embedding: torch.Tensor) -> torch.Tensor:
           # project to num_tokens pseudo-tokens in LLM space
           projected = self.projection(code_embedding)
           return projected.reshape(-1, self.num_tokens, self.llm_dim)
   ```

4. **Training requirements** — this requires:
   - A dataset of (codebase, question, answer) triples
   - Fine-tuning the projection layer (freeze code encoder + LLM, train projection)
   - SWE-bench or similar could provide training data
   - Estimated: significant GPU time, research-level effort

5. **Practical alternative: code summary embeddings**:
   If full neural embeddings are too speculative, implement a lighter version:
   - Use CodeBERT to embed each file
   - At query time, retrieve top-K most relevant files by embedding similarity
   - Only include those files in context (not the full codebase)
   - This is essentially Phase 5B (AST chunking) with neural retrieval

6. **Evaluation plan**:
   - Compare: full codebase in context vs neural embedding vs top-K retrieval
   - Metrics: task success rate, token count, response quality
   - On SWE-bench Lite subset (if benchmark data available)

### Files to create/modify
- `poor-cli/neural_code_encoder.py` (new, research prototype)
- `docs/NEURAL_CODE_EMBEDDINGS.md` (research findings)
- Training scripts (separate research directory)

### Acceptance criteria
- [ ] Architecture study complete (LLaVA → code analogy assessed)
- [ ] CodeBERT baseline: codebase → embedding → retrieval pipeline working
- [ ] Practical alternative (neural retrieval) prototyped
- [ ] Benchmarked against text-in-context baseline
- [ ] Documented: feasibility, training requirements, expected performance
- [ ] Recommendation: pursue or shelve, with evidence

### References
- [LLaVA](https://arxiv.org/abs/2304.08485) — architectural pattern
- [CodeBERT](https://arxiv.org/abs/2002.08155) — code embeddings
- [GraphCodeBERT](https://arxiv.org/abs/2009.08366) — graph-enhanced code embeddings
- [UniXcoder](https://arxiv.org/abs/2203.03850) — unified cross-modal code representation
