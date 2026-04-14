# core.py pre-slice placement map

[Inference] Target map for later PRDs; no logic moved in PRD 017.

| target module | current `core.py` region | notes |
|---|---:|---|
| `poor-cli/core_agent_loop.py` | 2820-3730 | `send_message_events`: streaming agent loop, tool/retry loop, cancellation, fallback, per-turn budget/economy events |
| `poor-cli/core_agent_loop.py` | 3731-3817 | `_stream_and_collect`: provider stream collection used by the tool loop |
| `poor-cli/core_agent_loop.py` | 4415-4567 | `send_message`: legacy streaming loop |
| `poor-cli/core_agent_loop.py` | 4671-4855 | `send_message_sync`: non-streaming loop |
| `poor-cli/core_tool_dispatch.py` | 283-453 | MCP/tool group declaration resolution and lazy activation |
| `poor-cli/core_tool_dispatch.py` | 1241-1766 | tool target inspection, permission audit helpers, permission scoping, checkpoint-before-mutation, per-turn cache key |
| `poor-cli/core_tool_dispatch.py` | 1768-1875 | `_execute_tool_internal`: hook gate, checkpoint, raw registry execution, audit, result cache |
| `poor-cli/core_tool_dispatch.py` | 3818-4327 | auto-permission, mutating/concurrency checks, result budgeting, single-call and batched function-call dispatch |
| `poor-cli/core_tool_dispatch.py` | 4568-4669 | legacy `_handle_function_calls` dispatch |
| `poor-cli/core_tool_dispatch.py` | 4857-4902 | public `execute_tool` / `execute_tool_raw` wrappers stay API-compatible on `PoorCLICore` |
| `poor-cli/core_tool_dispatch.py` | 5048-5201 | edit/read/write convenience wrappers and tool declaration shipping |
| `poor-cli/core_turn_lifecycle.py` | 862-906 | audit log and policy hook event helpers |
| `poor-cli/core_turn_lifecycle.py` | 973-1033 | prompt submission hooks, context/mutation/provider summaries |
| `poor-cli/core_turn_lifecycle.py` | 1033-1239 | cost deltas, run diagnostics, run start/finish metadata |
| `poor-cli/core_turn_lifecycle.py` | 1877-2295 | cost, economy, cache, context pressure/status reporting |
| `poor-cli/core_turn_lifecycle.py` | 2533-2585 | idle compaction timer and output token cap setup |
| `poor-cli/core_turn_lifecycle.py` | 5232-5430 | run/status/doctor/policy/MCP status surfaces |
| `poor-cli/core_turn_lifecycle.py` | 5431-5484 | shutdown/session-end cleanup |
| `poor-cli/core_turn_lifecycle.py` | 5503-5930 | context compaction lifecycle and transcript/pruning sidecars |
| later `ContextAssemblyOrchestrator` | 1273-1476 | instruction snapshot, skill context, context selection/message assembly, preview context |
| later `ContextAssemblyOrchestrator` | 2297-2473 | vision/downshift/cache eligibility and semantic/exact response cache hooks used during context-heavy turns |
| later `ContextAssemblyOrchestrator` | 2475-2531 | context dedup and diff-only read helpers |
| later `ContextAssemblyOrchestrator` | 2587-2818 | git context, working memory/repo graph workspace-map, token breakdown/context pressure, system context refresh |

Current verified `poor-cli/core.py` size: 6159 lines before scaffold-only edits.
