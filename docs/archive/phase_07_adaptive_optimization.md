# Phase 7: Adaptive Optimization — ML-Driven Token Management

**Priority:** Low-Medium — 🟠 Hard solutions requiring ML training or inference-layer access.
**Estimated agents:** 2 (parallel)
**Dependencies:** Phase 4B (model routing) is a prerequisite — RL budget allocation extends the routing concept. Phase 5A (LLMLingua) was the only shared-infra dependency after Phase 9B archived speculative decoding.
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
- `poor-cli/token_budget_controller.py` (new, ~400 lines)
- `poor-cli/budget_logger.py` (new, ~100 lines — data collection)
- Core engine (integrate controller into per-turn decision loop)
- `poor-cli/profiles.py` (controller respects economy mode constraints)

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

**Outcome:** Archived by Phase 9B. The repo had helper/test coverage but no end-to-end vLLM provider path, so `poor-cli/speculative_decoding.py`, its config surface, and its direct tests were removed.
