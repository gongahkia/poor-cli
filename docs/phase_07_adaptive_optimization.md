# Phase 7: Adaptive Optimization — ML-Driven Token Management

**Priority:** Low-Medium — 🟠 Hard solutions requiring ML training or inference-layer access.
**Estimated agents:** 2 (parallel)
**Dependencies:** Phase 4B (model routing) is a prerequisite — RL budget allocation extends the routing concept. Phase 5A (LLMLingua) shares infrastructure with speculative decoding.
**Philosophy:** Move from static heuristics to learned policies. Instead of hand-tuning thresholds for compaction, routing, and compression, learn them from actual usage patterns. These are the final "squeeze" optimizations before research-grade territory.

---

## Agent 7A: Reinforcement Learning Token Budget Allocation

**Pain points addressed:** Wrong-sized resources for task, overall cost optimization
**Solution reference:** Solution #17 from SOLUTIONS.md
**Expected savings:** Adaptive — learns optimal allocation over time, potentially 30-50% improvement over static heuristics

### What to build

A meta-controller that observes session state and learns to allocate token budgets optimally. It decides: how many thinking tokens to allow, which model to route to, how aggressively to compress, and when to trigger compaction — all based on learned policies rather than static thresholds.

### Implementation details

1. **State representation** — what the controller observes:
   ```python
   @dataclass
   class TokenBudgetState:
       task_complexity: float        # from Phase 4B classifier (0-1)
       context_utilization: float    # current_tokens / max_tokens (0-1)
       turn_number: int              # how deep into the session
       tool_calls_pending: int       # estimated remaining tool calls
       recent_failure_rate: float    # failures in last 5 turns (0-1)
       economy_mode: str             # frugal/balanced/quality
       provider: str                 # which provider is active
       model_tier: str               # cheap/mid/expensive
   ```

2. **Action space** — what the controller decides:
   ```python
   @dataclass
   class TokenBudgetAction:
       max_thinking_tokens: int      # 0 (disable) to 32000
       max_output_tokens: int        # 256 to 8192
       compression_ratio: float      # 0.0 (none) to 0.9 (heavy)
       model_tier: str               # cheap/mid/expensive
       should_compact: bool          # trigger compaction this turn?
       should_prune: bool            # trigger history pruning?
   ```

3. **Reward signal** — measure success:
   ```python
   def compute_reward(state, action, outcome):
       reward = 0.0
       # cost efficiency: fewer tokens = positive reward
       reward += -0.001 * outcome.total_tokens_used
       # task success: successful tool calls = positive
       reward += 1.0 if outcome.task_succeeded else -0.5
       # user satisfaction proxy: no retries needed = positive
       reward += 0.5 if not outcome.user_retried else -0.3
       # speed: faster response = positive
       reward += -0.01 * outcome.response_time_seconds
       return reward
   ```

4. **Training approach** — start simple, escalate:
   - **Phase 7A-1: Rule-based baseline** — implement the controller as a decision tree trained on logged session data. No neural network needed initially.
   - **Phase 7A-2: Contextual bandit** — upgrade to a contextual bandit (simpler than full RL) that learns per-state action preferences from feedback.
   - **Phase 7A-3: Full RL** — if data justifies it, train a small policy network.

5. **Data collection** — log every (state, action, outcome) tuple:
   ```python
   class BudgetLogger:
       def log(self, state: TokenBudgetState, action: TokenBudgetAction, 
               outcome: TurnOutcome):
           self.store.append({
               "timestamp": now(),
               "state": asdict(state),
               "action": asdict(action),
               "outcome": asdict(outcome),
           })
   ```
   Store in `.poor-cli/budget_logs.jsonl` for offline analysis.

6. **Integration** — the controller wraps all existing optimization decisions:
   - Before each turn: controller.decide(state) → action
   - Apply action: set thinking tokens, choose model, set compression
   - After turn: controller.observe(outcome)

7. **Safety constraints**:
   - Never reduce thinking tokens below provider minimum
   - Never set compression ratio above 0.9 (preserve core meaning)
   - In `quality` mode, controller is advisory only (user preferences override)
   - Fallback: if controller fails, use static heuristics from previous phases

### Files to create/modify
- `poor_cli/token_budget_controller.py` (new, ~400 lines)
- `poor_cli/budget_logger.py` (new, ~100 lines — data collection)
- Core engine (integrate controller into per-turn decision loop)
- `poor_cli/profiles.py` (controller respects economy mode constraints)

### Acceptance criteria
- [ ] State representation captures session dynamics
- [ ] Decision tree baseline makes reasonable budget decisions
- [ ] Session data logged for offline analysis
- [ ] Controller decisions improve over time (measure: tokens per successful task)
- [ ] Safety constraints prevent degenerate decisions
- [ ] Economy mode overrides controller when explicit
- [ ] Test: simulate 100 sessions, verify controller learns to use cheaper models for simple tasks
- [ ] Metric: compare tokens/task with and without controller over 50+ sessions

### References
- [Learning how hard to think](https://arxiv.org/abs/2410.04707)
- [Confident Adaptive Language Modeling (DeepMind)](https://arxiv.org/abs/2207.07061)
- [FrugalGPT](https://arxiv.org/abs/2305.05176) — the conceptual foundation

---

## Agent 7B: Speculative Decoding Integration

**Pain points addressed:** Per-token cost reduction, especially for predictable code generation
**Solution reference:** Solution #13 from SOLUTIONS.md
**Expected savings:** Up to 3× faster inference with identical output quality

### What to build

Integrate speculative decoding for local inference (Ollama/vLLM), pairing a small draft model with the main model to accelerate generation.

### Important caveat

Like Phase 6B, this **only works with self-hosted inference**. Closed APIs handle this server-side (if at all). This feature targets Ollama and vLLM users specifically.

### Implementation details

1. **How speculative decoding works**:
   ```
   Small model (0.5B) generates K draft tokens → 
   Large model verifies all K in one forward pass →
   Accept matching tokens (often 70-90% for code) →
   Reject and regenerate from first mismatch
   ```
   Net effect: K tokens for the cost of ~1 large-model forward pass.

2. **Draft model selection** — pair draft models with main models:
   ```python
   DRAFT_MODEL_PAIRS = {
       # main model → draft model
       "llama3.1:70b": "llama3.1:8b",
       "qwen2.5-coder:32b": "qwen2.5-coder:1.5b",
       "codellama:34b": "codellama:7b",
       "deepseek-coder-v2:33b": "deepseek-coder-v2:7b",
   }
   ```

3. **vLLM integration** — vLLM has native speculative decoding support:
   ```python
   # vLLM server launch with speculative decoding
   # vllm serve main_model --speculative-model draft_model --num-speculative-tokens 5
   ```
   If the user is running vLLM, detect and enable speculative decoding automatically.

4. **Ollama integration** — check if Ollama supports speculative decoding:
   - As of knowledge cutoff, Ollama may not have native speculative decoding
   - Investigate current Ollama API for any speculative decoding flags
   - If not supported, document the vLLM alternative

5. **EAGLE-3 approach** — if draft model pairing is complex, investigate EAGLE-3:
   - Uses prediction heads attached to the target model's internals
   - No separate draft model needed
   - Requires model modification — may only be feasible with custom models

6. **Configuration**:
   ```yaml
   speculative_decoding:
     enabled: true
     backend: "vllm"  # or "ollama" if supported
     draft_model: "auto"  # auto-detect from DRAFT_MODEL_PAIRS
     num_speculative_tokens: 5
   ```

7. **Metrics** — track acceptance rate and speedup:
   ```python
   class SpeculativeMetrics:
       total_draft_tokens: int = 0
       accepted_tokens: int = 0
       
       @property
       def acceptance_rate(self) -> float:
           return self.accepted_tokens / max(self.total_draft_tokens, 1)
       
       @property 
       def speedup_factor(self) -> float:
           # theoretical speedup based on acceptance rate
           k = 5  # num speculative tokens
           return k * self.acceptance_rate + 1
   ```

### Files to create/modify
- `poor_cli/speculative_decoding.py` (new, ~200 lines)
- `poor_cli/providers/ollama_provider.py` (add speculative decoding config)
- `.poor-cli/config.yaml` (add speculative_decoding section)
- `poor_cli/cost.py` (track speculative decoding metrics)

### Acceptance criteria
- [ ] Draft model auto-detected from DRAFT_MODEL_PAIRS
- [ ] vLLM speculative decoding works when vLLM is the backend
- [ ] Ollama support if API allows, otherwise documented as vLLM-only
- [ ] Acceptance rate and speedup tracked and displayed
- [ ] Feature gated behind local inference detection
- [ ] No effect when using closed API providers
- [ ] Test: generate 100 code completions, measure acceptance rate > 70%

### References
- [vLLM speculative decoding](https://docs.vllm.ai/en/latest/features/spec_decode/)
- [EAGLE-3 GitHub](https://github.com/SafeAILab/EAGLE)
- [Medusa](https://github.com/FasterDecoding/Medusa)
- [Speculative Sampling (DeepMind)](https://arxiv.org/abs/2302.01318)
