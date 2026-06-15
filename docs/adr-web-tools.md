# ADR: Web Tools

Status: accepted, 2026-06-15.

`web_search` and `web_fetch` are replayable tools, not shell escapes. Search is disabled by default. Fetch accepts only HTTP(S), blocks URL credentials, localhost, private/link-local/reserved IPs, denied domains, and redirects into blocked targets.

Threat model:
- SSRF through loopback, metadata, private network, DNS rebinding, or redirects.
- Unbounded content and prompt injection in fetched pages.
- Non-replayable external evidence.

Policy:
- `tools.web.mode = "custom"` uses a configured JSON search endpoint with strict result schema.
- `tools.web.mode = "native"` records provider-hosted search intent only when the selected provider profile advertises `web = true`.
- `tools.web.mode = "free"` is best-effort and test-isolated.
- `web_fetch` stores sanitized content, byte count, truncation, content hash, final URL, cache metadata, and citation artifacts.
- `respect_robots = true` makes robots.txt a compliance gate. It is not treated as a security boundary.

Residual risk: DNS resolution failures are allowed so offline/test environments can still use explicit allowlists; production configs should prefer `allow_domains`.
