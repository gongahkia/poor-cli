# Security Policy

## Reporting A Vulnerability

Do not open a public issue for vulnerabilities, exposed secrets, authentication bypasses, data-leak paths, supply-chain compromise, or abuse cases that could harm users.

Send a private report to `maintainers@sg-apis` with:

- affected component or package
- reproduction steps or proof of concept
- expected impact
- whether any secrets, personal data, or restricted upstream data may be exposed
- suggested remediation, if known

The maintainer team should acknowledge reports within 5 business days, triage severity, and coordinate a fix or mitigation before public disclosure.

## Supported Scope

Security reports are in scope when they affect:

- Dude web app code
- Dude MCP server/runtime
- package publishing or release artifacts
- HTTP gateway auth, toolset policy, or remote deployment behavior
- export artifacts that may leak source data, secrets, or unsupported personal data
- contributor, CI, or release workflows

## Production Dependency Audit Policy

CI and release preflight run:

```bash
npm run security:audit:prod
```

The gate evaluates `npm audit --omit=dev` so development-only advisories do not block runtime releases. High and critical production findings fail the gate unless they are fixed or explicitly allowlisted with rationale. Moderate findings require a tracking reference or allowlist entry.

Allowlist entries live in `config/npm-audit-allowlist.json`. Each entry must include `package`, `severity`, `advisoryId` or `title`, `rationale`, and `tracking`. Empty or undocumented allowlist entries fail the gate.

## Out Of Scope

- General legal, tax, investment, credit, or licensed-advisor questions.
- Claims that an upstream public dataset is inaccurate unless Dude transforms it incorrectly.
- Denial-of-service reports that rely only on high-volume public endpoint traffic without a practical mitigation.

## Disclosure

Security fixes should include release notes once the vulnerability is remediated. If a report affects upstream data licensing, privacy, or hosted-user obligations, maintainers should also update the relevant governance, privacy, or public-data-limits docs.
