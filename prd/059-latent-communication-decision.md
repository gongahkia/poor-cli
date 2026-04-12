# PRD 059: Latent communication — ship for Ollama or archive

- **Wave:** 3
- **Status:** decision
- **Estimated effort:** small (1d) if archive; x-large (3w+) if ship
- **Blocked by:** 008
- **Files it mutates:**
  - `poor_cli/research/latent_communication.py` (or deleted)
  - `docs/LATENT_COMMUNICATION.md`
  - `poor_cli/sub_agent.py`, `poor_cli/parallel_agents.py` (if shipping — integration points)

## 1. Problem

LatentMAS prototype documents 70–84% token reduction on multi-agent hops for local open-weight models. Three years of research notes; zero user-facing integration. The in-between state is worst-of-both. LEARNING.md §1.5, §4.3.

## 2. Current state

Code complete; not wired to agent loop; requires open-weight model + local GPU; API-closed providers (Anthropic, OpenAI) can't benefit.

## 3. Decision required

> **DECISION REQUIRED:**
> - (a) **Ship for Ollama / vLLM users only.** Gated behind `ProviderCapability.LATENT_COMMUNICATION`. Integrate with `sub_agent.py` + `parallel_agents.py`. 3+ weeks of work. Payoff: unique differentiator for local-model users.
> - (b) **Archive.** Delete `research/latent_communication.py`. Update docs to state "ceased."
> - (c) **Freeze.** Keep as research artifact; disable imports; update docs.

**Recommended:** (a) if local users are a target audience (PRD 062 will clarify); (b) otherwise.

## 4. Design (if (a))

- `ProviderCapability.LATENT_COMMUNICATION` (PRD 020).
- `LatentChannel` — sub-agent-to-sub-agent hidden-state hand-off. Text fallback if channel unavailable.
- Benchmark harness on Qwen3 or Llama-4.
- Docs: user guide.

## 5. Files to create / modify / delete

Depends on decision.

## 6. Implementation plan

Depends on decision. Spawn follow-up PRDs for (a).

## 7. Testing & acceptance criteria

If (a): integration test with two Ollama sub-agents; assert token count drops.
If (b): `latent_communication.py` gone; docs updated.
If (c): module raises `NotImplementedError` on import.

## 8. Rollback / risk

If (a): reverting is reverting integration. If (b): restore from git.

## 9. Out-of-scope & boundary

- 🚫 Do not ship for closed-API providers.

## 10. Related PRDs & references

- PRD 008, 020, 062.
- LEARNING.md §1.5, §4.3.
