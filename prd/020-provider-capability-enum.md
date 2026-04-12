# PRD 020: Introduce `ProviderCapability` enum

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (1.5w)
- **Blocks:** 027, 030
- **Blocked by:** 017
- **Files it mutates:**
  - `poor_cli/providers/base.py`
  - `poor_cli/providers/*_provider.py` (all adapters)
  - `poor_cli/provider_catalog.py`
  - `poor_cli/core.py` (narrow — feature gating call sites only)
  - `poor_cli/thinking_budget.py`
  - `poor_cli/vision.py`
- **New files it adds:**
  - `poor_cli/providers/capability.py`
  - `tests/test_provider_capability.py`

## 1. Problem

Extended thinking is hardcoded to Anthropic (`ThinkingBudgetOptimizer`). Prompt caching is Anthropic-only in code but not declared as such. Gemini grounding is not exposed. Provider-specific features are scattered, not typed. LEARNING.md §2.1: "Extended thinking is baked into core; should be provider capability."

## 2. Current state

`providers/base.py` has abstract methods for the common surface but no capability flags. Callers check `isinstance(provider, AnthropicProvider)` to decide whether to use caching or thinking.

## 3. Goal & non-goals

**Goal:** `ProviderCapability` enum that every provider declares. Core queries capabilities via `provider.capabilities`. Conditional code paths use enum checks, not `isinstance`.

**Non-goals:**
- Do not implement new capabilities (e.g., latent communication) here — just type them.
- Do not change SDK usage.

## 4. Design

```python
# poor_cli/providers/capability.py
from enum import Flag, auto

class ProviderCapability(Flag):
    NONE                   = 0
    STREAMING              = auto()
    TOOL_CALLING           = auto()
    SYSTEM_INSTRUCTIONS    = auto()
    JSON_MODE              = auto()
    VISION                 = auto()
    PROMPT_CACHING_PREFIX  = auto()
    PROMPT_CACHING_BLOCK   = auto()
    EXTENDED_THINKING      = auto()
    GROUNDING              = auto()   # Gemini web search
    LATENT_COMMUNICATION   = auto()   # for research mode

class BaseProvider(ABC):
    capabilities: ProviderCapability = ProviderCapability.NONE
    ...
```

Each adapter declares its set:

```python
class AnthropicProvider(BaseProvider):
    capabilities = (
        ProviderCapability.STREAMING |
        ProviderCapability.TOOL_CALLING |
        ProviderCapability.SYSTEM_INSTRUCTIONS |
        ProviderCapability.VISION |
        ProviderCapability.PROMPT_CACHING_PREFIX |
        ProviderCapability.EXTENDED_THINKING
    )
```

Core code:

```python
if ProviderCapability.EXTENDED_THINKING in provider.capabilities:
    thinking_budget = self._thinking.allocate(...)
else:
    thinking_budget = 0
```

## 5. Files to create / modify / delete

**Create**
- `poor_cli/providers/capability.py`
- `tests/test_provider_capability.py`

**Modify**
- `poor_cli/providers/base.py` — add `capabilities` attribute.
- Each `poor_cli/providers/*_provider.py` — declare capabilities.
- `poor_cli/provider_catalog.py` — expose capabilities in the catalog for UIs.
- `poor_cli/core.py` — narrow: replace `isinstance` checks with capability checks.
- `poor_cli/thinking_budget.py` — refuse allocation for providers without the cap.

## 6. Implementation plan

1. Land `capability.py`.
2. Add to `BaseProvider`.
3. Declare capabilities per adapter.
4. Replace `isinstance` gates in core.
5. Tests: each adapter's capability set; each gate.
6. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_anthropic_has_extended_thinking`
- `test_openai_has_streaming`
- `test_ollama_has_no_prompt_caching`
- `test_thinking_allocation_refused_without_capability`

**Done criterion**
- [ ] Enum exists, every provider declares.
- [ ] No `isinstance(provider, *Provider)` feature gate remains in core code paths.

## 8. Rollback / risk

Low. Behavior-preserving.

## 9. Out-of-scope & boundary

- 🚫 Do not implement new capabilities.
- 🚫 Do not change provider SDK usage.

## 10. Related PRDs & references

- PRD 027 (block-level caching) keys on `PROMPT_CACHING_BLOCK`.
- PRD 030 (picker) can gray out options based on capabilities.
- LEARNING.md §2.1, §6.
