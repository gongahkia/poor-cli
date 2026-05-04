# Phase A — Foundation

**Goal:** ship the lowest-risk, highest-visibility token-aware features. These prove the harness story without touching the agent loop.

**Order (commit each separately):**
1. Live token HUD in TUI
2. Slash-command autocomplete in TUI composer
3. Hook events expansion 12 → 26

**Cross-cutting rules:**
- One git commit per feature. Commit message format: `feat(<area>): <one-line>` with body explaining the change. Co-Author trailer per repo convention.
- Run `python3 -m pytest tests/ --ignore=tests/test_mcp_multi_server.py --ignore=tests/test_mcp_transport.py --ignore=tests/test_kv_cache.py --ignore=tests/test_structured_output_parity.py` after each feature. Must stay green (1681 baseline).
- No new third-party deps for Phase A. Stdlib + `textual` + `rich` only.
- Follow `CLAUDE.md`: terse comments lowercase, no auto-refactor, no whitespace bloat.

---

## A1 — Live token HUD in TUI

### Goal
Surface `token_budget_controller` decisions, `adaptive_budget` retuning state, compaction/pruning triggers, and projected cost in the TUI activity pane and a new compact HUD line. Make the harness obviously token-aware to the operator.

### Data flow (current, verified)
- `poor_cli/token_budget_controller.py` — `TokenBudgetState`, `TokenBudgetAction`, `TurnOutcome`, `compute_reward()`, `RuleBasedController`.
- `poor_cli/adaptive_budget.py` — `AdaptiveBudgetController`, `AdaptationStats` (already has `to_dict()`).
- `poor_cli/budget_logger.py` — per-turn budget log writer.
- TUI: `poor_cli/tui/textual_app.py` — single `#status` Static at top, `#activity` Static on the right.
- RPC layer: `poor_cli/server/handlers/` — handlers grafted via `_HANDLER_ORDER` in `__init__.py`.

### Files to create
- `poor_cli/server/handlers/budget_hud.py` — new handler module.
- `tests/test_budget_hud_handler.py`.

### Files to modify
- `poor_cli/server/handlers/__init__.py` — append `"budget_hud"` to `_HANDLER_ORDER` (just before `"mcp"`).
- `poor_cli/server/registry.py` — append `"budget_hud"` to its `_HANDLER_ORDER`.
- `poor_cli/server/registry_static_index.json` — add handler to `handlerOrder`, register new RPC `poor-cli/budgetHudSnapshot` in `rpcIndex`, add handler attrs to `attrIndex`.
- `poor_cli/tui/textual_app.py` — add HUD line widget + poll loop.
- `poor_cli/tui/rpc_client.py` — no change (uses generic `call`).

### Implementation

**`poor_cli/server/handlers/budget_hud.py`:**
```python
# ruff: noqa: F403,F405
from __future__ import annotations
from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class BudgetHudHandlersMixin:
    def _budget_hud_payload(self) -> Dict[str, Any]:
        core = getattr(self, "_core_instance", None)
        adapt = getattr(core, "_adaptive_budget", None) if core else None
        last_action = getattr(core, "_last_budget_action", None) if core else None
        last_outcome = getattr(core, "_last_turn_outcome", None) if core else None
        stats = adapt.stats().to_dict() if adapt else {}
        return {
            "lastAction": last_action.__dict__ if last_action else {},
            "lastOutcome": last_outcome.__dict__ if last_outcome else {},
            "adaptation": stats,
            "ts": _utc_now(),
        }

    async def handle_budget_hud_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        return self._budget_hud_payload()


@register("poor-cli/budgetHudSnapshot")
async def _rpc_budget_hud_snapshot(ctx, params):
    return await ctx.handle_budget_hud_snapshot(params)
```

(Implementer: if `_core_instance`, `_adaptive_budget`, `_last_budget_action`, `_last_turn_outcome` attributes do not exist, add them as the budget controller / adaptive controller is invoked in `core_turn_lifecycle.py`. Search for `RuleBasedController` and `AdaptiveBudgetController` instantiation; assign last-action and last-outcome as side-effects of `decide_action` / `record_outcome`.)

**TUI changes (`poor_cli/tui/textual_app.py`):**
- Add a new `Static` widget id `#hud` between `#status` and `#main`. CSS height 1, dim color, padding 0 1.
- In `__init__`: `self._hud_inflight = False`, `self._hud_text = ""`.
- In `on_mount`: `self.set_interval(2.0, self._poll_hud)`.
- New method:
  ```python
  def _poll_hud(self) -> None:
      if self._connection_state != "connected" or self._hud_inflight:
          return
      self._hud_inflight = True
      self._start_rpc_request("HUD", "poor-cli/budgetHudSnapshot", {}, event_type="hud_snapshot", timeout=3.0)
  ```
- In `_handle_ui_event`, add branch:
  ```python
  if event_type == "hud_snapshot":
      self._hud_inflight = False
      self._render_hud(event.get("result"))
      return
  ```
- New method `_render_hud(result)` formats one-line: `tok in/out/think | comp X% | mode <frugal|balanced|quality> | trend <±0.NN>`.

### Test plan
`tests/test_budget_hud_handler.py`:
- Build a fake context object with `_last_budget_action`, `_last_turn_outcome`, `_adaptive_budget` attrs; assert `handle_budget_hud_snapshot` returns expected keys (`lastAction`, `lastOutcome`, `adaptation`, `ts`).
- Test missing-state graceful path returns empty dicts (not exceptions).

### Acceptance
- `poor-cli tui` starts; HUD line appears once a turn has run; updates every 2s.
- Pytest green.

### Commit
```
feat(tui): live token HUD surfaces budget controller and adaptation state

Adds poor-cli/budgetHudSnapshot RPC and a one-line HUD widget polled
every 2s in the TUI. Surfaces the rule-based controller's last action,
last turn outcome, and adaptive_budget trend. No agent-loop changes;
HUD reads side-effect attributes set by the existing controller paths.
```

---

## A2 — Slash-command autocomplete in TUI composer

### Goal
Inline autocomplete in the composer over `command_manifest.json` + custom commands. `/` prefix triggers a popup with fuzzy match, arg hints, and descriptions.

### Verified anchors
- `poor_cli/command_manifest.json` — list of commands with `command`, `description`, `category`, `recommended`.
- `poor_cli/command_manifest.py` — `load_command_manifest()` returns `CommandManifest`.
- `poor_cli/custom_commands.py` — repo-local custom slash commands.
- TUI composer: `Input` widget id `#composer` in `compose()`.

### Files to create
- `poor_cli/tui/autocomplete.py` — match + suggestion source.
- `tests/test_autocomplete_source.py`.

### Files to modify
- `poor_cli/tui/textual_app.py` — add suggestion popup (`Static` widget id `#suggest`), key handling, intercept `Tab`/`↑`/`↓`/`Enter`.

### Implementation

**`poor_cli/tui/autocomplete.py`:**
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from poor_cli.command_manifest import load_command_manifest, CommandSpec
from poor_cli.custom_commands import load_custom_commands


@dataclass(frozen=True)
class Suggestion:
    command: str
    description: str
    category: str


def all_suggestions() -> List[Suggestion]:
    manifest = load_command_manifest()
    items = [Suggestion(c.command, c.description, c.category) for c in manifest.commands]
    try:
        for name, body in load_custom_commands().items():
            items.append(Suggestion(f"/{name}", str(body.get("description", "")).strip(), "custom"))
    except Exception:
        pass
    return items


def fuzzy_match(query: str, items: List[Suggestion], limit: int = 8) -> List[Suggestion]:
    q = query.lower().lstrip("/")
    if not q:
        return [s for s in items if s.command.startswith("/")][:limit]
    scored = []
    for s in items:
        name = s.command.lstrip("/").lower()
        if name.startswith(q):
            scored.append((0, s))
        elif q in name:
            scored.append((1, s))
        elif all(ch in name for ch in q):
            scored.append((2, s))
    scored.sort(key=lambda t: (t[0], len(t[1].command)))
    return [s for _, s in scored[:limit]]
```

**TUI integration (`poor_cli/tui/textual_app.py`):**
- Add `from .autocomplete import Suggestion, all_suggestions, fuzzy_match`.
- In `__init__`: `self._suggestions: List[Suggestion] = []`, `self._suggestion_index = 0`, `self._suggest_visible = False`. Lazy-load `self._all_suggestions = all_suggestions()` in `on_mount`.
- In `compose()`: insert `yield Static("", id="suggest")` directly above the `Input`. CSS: `height: auto; max-height: 8; background: #1c1b18; color: #e7ddb5; padding: 0 1; display: none;`.
- Hook `Input.Changed`:
  ```python
  def on_input_changed(self, event: Input.Changed) -> None:
      text = event.value
      if text.startswith("/"):
          self._suggestions = fuzzy_match(text, self._all_suggestions)
          self._suggestion_index = 0
          self._render_suggestions()
      else:
          self._hide_suggestions()
  ```
- Add `BINDINGS` for `tab`, `up`, `down`, `escape` to navigate / accept / hide.
- `_render_suggestions()` updates `#suggest` content with up to 8 lines, marking current with `▶`.
- `_accept_suggestion()` writes selected `command + " "` into `#composer` and hides popup.

### Test plan
`tests/test_autocomplete_source.py`:
- `fuzzy_match("/com")` returns commands starting with `com` first.
- Empty query returns top-N starting with `/`.
- Custom command discovery does not blow up if `.poor-cli/commands` dir is missing.

### Acceptance
- Typing `/` shows popup. `Tab`/`↑`/`↓` navigate. `Enter` accepts selection. `Esc` dismisses.
- Pytest green.

### Commit
```
feat(tui): slash-command autocomplete popup over manifest + custom

Adds inline composer autocomplete that surfaces command_manifest.json
and any custom commands. Fuzzy match (prefix > substring > subseq).
Tab/Up/Down/Esc keybindings. Popup hides outside of /-prefixed input.
```

---

## A3 — Hook events expansion 12 → 26

### Goal
Match Claude Code's hook coverage so the existing `PolicyHookManager` becomes a fully programmable governance surface. No semantics change for existing 12 events.

### Current state (verified, `poor_cli/policy_hooks.py` line 22)
12 events: `session_start, user_prompt_submitted, permission_decision, pre_tool_use, post_tool_use, tool_failure, task_started, task_finished, automation_started, automation_finished, checkpoint_restored, session_end`.

### New events to add (target 26 total)
Add the following 14 events to `HOOK_EVENTS` (preserve existing order, append):
- `notification` — fired when `_add_activity` posts a user-visible event the operator should see (mirror Claude Code's `Notification`).
- `subagent_stop` — fires when a sub-agent run finishes (success or failure).
- `subagent_start` — fires when a sub-agent run begins.
- `pre_compact` — fires before `context_compressor.py` runs a compaction.
- `post_compact` — fires after compaction with delta token info.
- `pre_prune` — fires before `history_pruning.py` runs.
- `post_prune` — fires after prune with rows-removed count.
- `pre_checkpoint` — fires before a checkpoint is taken.
- `post_checkpoint` — fires after, with checkpoint id.
- `pre_edit` — fires before any write tool commits (read-only inspection of pending edit).
- `post_edit` — fires after a write tool commits, with diff summary.
- `pre_provider_call` — fires immediately before each provider request, payload includes `tokensIn`, `provider`, `model`.
- `post_provider_call` — fires immediately after, payload includes `tokensOut`, `latencyMs`, `cost`.
- `budget_breach` — fires when `token_budget_controller`'s safety clamp activates (hard cap reached).

### Files to modify
- `poor_cli/policy_hooks.py` — extend `HOOK_EVENTS` tuple.
- `poor_cli/lifecycle_events.py` — extend any event-name registry it owns.
- `poor_cli/core_turn_lifecycle.py` — find existing `PolicyHookManager.run(...)` callsites; add new firing sites in correct lifecycle locations. Search for these strings: `"pre_tool_use"`, `"post_tool_use"`, `"checkpoint"`, `"compact"`. Wrap pre/post pairs around the operations identified.
- `poor_cli/context_compressor.py` — emit `pre_compact` / `post_compact`.
- `poor_cli/history_pruning.py` — emit `pre_prune` / `post_prune`.
- `poor_cli/checkpoint.py` — emit `pre_checkpoint` / `post_checkpoint`.
- `poor_cli/sub_agent.py` — emit `subagent_start` / `subagent_stop`.
- `poor_cli/edit_staging.py` (or wherever writes commit) — emit `pre_edit` / `post_edit`.
- `poor_cli/providers/base.py` (or per-provider call site) — emit `pre_provider_call` / `post_provider_call`.
- `poor_cli/token_budget_controller.py` `_clamp_action` — fire `budget_breach` when clamp adjusts a value.

### Hook payload schema (per new event)
Document inline in `policy_hooks.py` or a new `docs/HOOKS.md`. Each event's `payload` dict at minimum includes `event`, `ts`, `sessionId`. Specific extras:
- `notification`: `{title, detail, severity}`.
- `subagent_start`/`stop`: `{subagentId, archetype, parentRequestId, status?, duration_ms?}`.
- `pre_compact`/`post_compact`: `{tokensBefore, tokensAfter?, ratio}`.
- `pre_prune`/`post_prune`: `{rowsBefore, rowsAfter?, removed?}`.
- `pre_checkpoint`/`post_checkpoint`: `{checkpointId?, reason}`.
- `pre_edit`/`post_edit`: `{path, hunks, editId, status?}`.
- `pre_provider_call`/`post_provider_call`: `{provider, model, tokensIn, tokensOut?, latencyMs?, costUsd?}`.
- `budget_breach`: `{field, requested, clamped, limit}`.

### Test plan
- Extend `tests/test_policy_hooks.py` (find existing) with cases for each new event:
  - Hook file declaring each new event loads without validation error.
  - Firing the event invokes the configured command and passes the documented payload via stdin.
- New `tests/test_hook_event_emission.py`: smoke-test that each emission point compiles (import + monkeypatch `PolicyHookManager.run` to capture calls).

### Acceptance
- `HOOK_EVENTS` length is 26.
- Each new event fires at least once in a documented end-to-end path.
- Pytest green.

### Commit
```
feat(hooks): expand policy hook surface 12 -> 26 events

Adds notification, subagent_start/stop, pre/post compact, pre/post prune,
pre/post checkpoint, pre/post edit, pre/post provider_call, budget_breach.
Each event documents its payload shape and is fired at the appropriate
lifecycle site. Existing 12 events are unchanged.
```

---

## End-of-phase checklist

- [ ] 3 commits on `main` (or feature branch).
- [ ] Pytest green.
- [ ] `git log --oneline -3` shows the 3 phase-A commits in reverse order.
- [ ] HUD visible in TUI; autocomplete works; `policy_hooks.HOOK_EVENTS` length is 26.
