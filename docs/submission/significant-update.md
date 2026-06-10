# Significant Update Narrative

Swee SG was significantly updated after May 18, 2026 for the Splunk Agentic Ops Hackathon security track.

## Built After Submission Open

- Added Shield-governed Splunk MCP proxy tools: `splunk_search`, `splunk_list_indexes`, `splunk_list_saved_searches`, and `swee_shield_splunk_investigation_pack`.
- Added an upstream Splunk MCP client using the official MCP SDK Streamable HTTP transport.
- Added Splunk config plumbing through `SPLUNK_MCP_URL`, `SPLUNK_MCP_TOKEN`, keystore fallback for `splunk_mcp`, and optional `SPLUNK_MCP_ALLOWED_INDEXES`.
- Added output schemas for Splunk proxy, index list, saved-search list, Shield audit, approval, and simulator tools.
- Added policy simulator and red-team corpus for destructive SPL, prompt injection, fake secrets, oversized outputs, and bad indexes.
- Added human approval queue for broad/unbounded Splunk search shapes through `SWEE_SHIELD_APPROVAL_MODE=queue`.
- Added MCP evidence resources under `swee://shield/audits/{auditId}`, `swee://shield/approvals/{approvalId}`, and `swee://shield/redteam/corpus`.
- Added runtime output defense at Shield enforcement: credential/PII-shaped output redaction, prompt-injection neutralization, and optional critical-finding block mode.
- Added audit persistence for runtime findings and dual hashes: raw upstream output hash plus post-redaction output hash.
- Extended the dashboard Shield audit panel with investigation pack, policy simulator, approval queue, finding counts, reason codes, severity/action summaries, and short hash evidence.
- Added root `architecture_diagram.md` and synthetic demo fixtures for token-independent verification.

## Unchanged Boundaries

- No deterministic replay is claimed. Replay remains inspection-only metadata plus hashes.
- No live Splunk results are fabricated. Synthetic fixtures are labeled as fake demo events.
- No agent should call Splunk directly in the demo architecture; Splunk access goes through Shield proxy tools.
- Runtime scanner is deterministic and local-only; it does not call an AI model or network service.
