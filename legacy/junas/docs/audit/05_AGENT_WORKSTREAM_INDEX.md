# Independent Agent Workstreams

Each workstream below is designed for an independent coding agent with a mostly disjoint write scope.

## Workstreams
- [10_WORKSTREAM_A_WORKSPACE_SHELL.md](./10_WORKSTREAM_A_WORKSPACE_SHELL.md)
- [11_WORKSTREAM_B_DESIGN_SYSTEM.md](./11_WORKSTREAM_B_DESIGN_SYSTEM.md)
- [12_WORKSTREAM_C_API_LAYER_UNIFICATION.md](./12_WORKSTREAM_C_API_LAYER_UNIFICATION.md)
- [13_WORKSTREAM_D_CHAT_AND_COMMANDS.md](./13_WORKSTREAM_D_CHAT_AND_COMMANDS.md)
- [14_WORKSTREAM_E_TOOL_MIGRATION.md](./14_WORKSTREAM_E_TOOL_MIGRATION.md)
- [15_WORKSTREAM_F_BACKEND_ACTION_CONTRACT.md](./15_WORKSTREAM_F_BACKEND_ACTION_CONTRACT.md)
- [16_WORKSTREAM_G_QA_TELEMETRY_DOCS.md](./16_WORKSTREAM_G_QA_TELEMETRY_DOCS.md)

## Suggested Order
1. C + F in parallel (data contract foundation)
2. A + B in parallel (workspace shell + design primitives)
3. D + E in parallel (interaction + feature migration)
4. G last (hardening, tests, release docs)

## Shared Rules
- No legal text payloads via GET query params after migration.
- All user-triggered async actions must expose `loading`, `success`, `error`, and `retry`.
- All command palette items must map to executable actions.
- Preserve existing route compatibility until cutover is approved.

