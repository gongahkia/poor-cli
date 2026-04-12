# PRD 064: Consolidate extension model — DECISION + DESIGN

- **Wave:** 4
- **Status:** decision
- **Owner (human):** @gongahkia
- **Estimated effort:** medium if executed (2w)
- **Blocks:** —
- **Blocked by:** —

## 1. Problem

Four overlapping extensibility mechanisms:
- **Skills** (`poor_cli/skills.py`, `poor_cli/skill_surfacer.py`, `poor_cli/skills/*.md`) — instruction-driven.
- **Custom commands** (`poor_cli/custom_commands.py`) — slash commands.
- **Workflow templates** (`poor_cli/workflow_templates.py`) — multi-step macros.
- **Automation manager** (`poor_cli/automation_manager.py`) — scheduled / event-driven.

They do overlapping things. Users face option paralysis. Maintenance multiplies. LEARNING.md §4.1.

## 2. Current state

Four modules, four concepts, four docs, zero consolidation.

## 3. Decisions required

> **DECISION:**
> - (a) **Merge.** One `AutomationRule` type that can be triggered by cron, event, or slash command; absorb workflows. Keep skills separate (different concept — instruction libraries). Reduces from 4 to 2.
> - (b) **Keep four separate.**
> - (c) **Partial merge:** collapse custom_commands + workflow_templates; keep automations and skills separate. Reduces to 3.

**Recommended:** (a) — cleanest user-model, minimal loss.

## 4. Design (if (a))

```python
@dataclass
class AutomationRule:
    id: str
    name: str
    triggers: list[Trigger]            # cron | event | slash
    steps: list[Step]                  # prompt, tool_call, shell
    enabled: bool
    scope: Literal["repo","user"]
```

Migration: each existing workflow / custom-command / automation becomes an `AutomationRule`. One-shot converter; back up originals.

## 5. Files to modify

All four modules consolidate into `poor_cli/automations/`. Migration scripts for existing user data.

## 6. Implementation plan

If (a): spawn follow-up PRD with concrete migration steps.

## 7. Testing & acceptance criteria

- Every existing workflow / custom command / automation round-trips through the new type.
- `/workflow`, `/automation`, `/commands` all work post-consolidation or are aliased.

## 8. Rollback / risk

Medium. Migration is one-way; keep the migration script idempotent + back up `.poor-cli/`.

## 9. Out-of-scope & boundary

- 🚫 Do not consolidate skills (different concept).

## 10. Related PRDs & references

- LEARNING.md §4.1.
