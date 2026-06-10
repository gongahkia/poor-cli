# Claims Audit

Use this before publishing README copy, architecture diagrams, slides, or video narration.

## Allowed Claims

- Swee Shield wraps Splunk proxy tools with pre-flight policy and local audit metadata.
- Splunk proxy tools call the Splunk MCP Server through the official MCP SDK Streamable HTTP client.
- Audit rows include sanitized input, policy decision, runtime findings, output hash, and raw output hash.
- Runtime scanner redacts credential/PII-shaped strings and neutralizes prompt-injection-shaped strings before returning output to the caller.
- `SWEE_SHIELD_RUNTIME_SCAN_MODE=block` blocks critical runtime scanner findings.
- Synthetic demo fixtures prove scanner and audit behavior without a Splunk token.
- Live Splunk use requires `SPLUNK_MCP_URL` and `SPLUNK_MCP_TOKEN`.
- Splunk upstream RBAC remains part of the live security boundary.

## Forbidden Claims

- Deterministic replay.
- Full raw Splunk output storage.
- Guaranteed prevention of all prompt injection or data leakage.
- Splunk cannot sanitize this.
- Synthetic fixture events are live Splunk data.
- The local readiness endpoint proves live Splunk auth works.
- Missing Splunk evidence means an environment is safe, clean, or compliant.

## Required Qualifiers

- Runtime scanning is deterministic regex-based defense at the proxy boundary.
- The audit trail is tamper-evident and hash-verified, not a full replay system.
- Fixture-based tests are synthetic proof artifacts.
- Live E2E remains unverified until a real Splunk MCP URL and bearer token are configured.

