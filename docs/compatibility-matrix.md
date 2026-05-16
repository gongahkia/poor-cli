# Compatibility Matrix

## Scope

This matrix tracks environments we validate for day-2 adoption.
Support tiers are intentionally explicit so teams know what is verified versus best effort.

## MCP Client Matrix

| Client / Environment | Transport | Auth Mode | Tier | Validation Path | Notes |
| --- | --- | --- | --- | --- | --- |
| MCP Inspector (local) | stdio | none | `tier-1` | `npm run test:smoke:packaging` | Primary local inspection path. |
| Claude Desktop (local server) | stdio | none / key-based upstream creds | `tier-1` | `npm run quick-start` + `npm run test:smoke:live` | Best onboarding path for direct tool and `sg_query` testing. |
| Cursor / VS Code MCP clients | stdio | none / key-based upstream creds | `tier-1` | `npm run test:smoke:packaging` + profile smoke | Uses same `server.json` metadata and command wiring as registry installs. |
| Remote MCP over Streamable HTTP | streamable HTTP (`/mcp`) | `none` / `mixed` / `all` | `tier-1` | `npm run test:smoke:remote` | OIDC and bearer-mode checks live in `http-auth` regression tests. |
| REST gateway consumers (`/api/tools/*`) | HTTP JSON | bearer when enabled | `tier-2` | `packages/mcp-server/src/tools/__tests__/gateway-toolset.test.ts` | Supported for tool invocation parity and profile filtering. |
| Legacy SSE MCP clients | SSE | none / bearer | `tier-3` | manual only | Not a primary target; use Streamable HTTP where possible. |

## Runtime Matrix

| Runtime | OS | Tier | Validation Path | Notes |
| --- | --- | --- | --- | --- |
| Node.js 20.x | Linux (CI) | `tier-1` | `npm run verify` in CI | Canonical release path. |
| Node.js 20.x | macOS | `tier-1` | local `npm run verify` | Maintainer parity path. |
| Node.js 20.x | Windows (WSL or native) | `tier-2` | packaging smoke + manual quick-start | Expected to work; not primary release gate. |
| Node.js 22.x | Linux/macOS | `tier-2` | local smoke and workflow tests | Allowed but not release-blocking today. |

## Transport/Auth Matrix

| Deployment Shape | Transport | Server Auth | Upstream Auth Handling | Recommended Smoke |
| --- | --- | --- | --- | --- |
| Local developer run (`npx -y @dude/mcp`) | stdio | none | env or keystore per upstream | `npm run quick-start` |
| Registry/package install | stdio | none | env or keystore per upstream | `npm run test:smoke:registry` |
| Containerized remote (`/mcp`) | streamable HTTP | `none` / `mixed` / `all` | env or keystore per upstream | `npm run test:smoke:container` + `npm run test:smoke:remote` |
| REST gateway sidecar | HTTP JSON | optional bearer | env or keystore per upstream | gateway toolset tests + targeted live smoke |

## Support Policy

- `tier-1`: release-blocking coverage in CI or mandatory pre-release smoke.
- `tier-2`: expected to work with regular maintainer validation, but not fully release-blocking.
- `tier-3`: community/best-effort support; validate in your environment before production rollout.
