# Workspace Auth and RBAC

This is the implementation contract for issues #43 and #44.

## Architecture

Dude supports three deployment modes:

- Self-host local mode: no auth headers are required. The REST gateway resolves a local admin session so existing single-user deployments keep working.
- Hosted/workspace mode: set `DUDE_WORKSPACE_AUTH_REQUIRED=true`. API requests must include `x-dude-workspace-id`, `x-dude-actor-id`, `x-dude-role`, and `x-dude-2fa-verified`.
- Production fail-closed mode: with `NODE_ENV=production`, the REST gateway requires workspace headers unless workspace auth, protected OIDC HTTP config, or the explicit local safe-mode override is configured. Use `DUDE_ALLOW_INSECURE_PRODUCTION_LOCAL_AUTH=true` only for private, operator-controlled deployments where another layer already blocks public access.

The shared role model is:

| Role | Intended user | Key permissions |
| --- | --- | --- |
| `admin` | Workspace owner/security admin | workspace/member management, searches, dossiers, memos, exports, bulk, watchlists, audit, debug logs |
| `analyst` | CDD analyst | searches, dossiers, memos, exports, bulk, watchlists, audit |
| `viewer` | Reviewer/auditor | read dossiers, export, audit |

Cross-workspace isolation is enforced in store helpers by filtering every dossier, audit event, watchlist item, alert, and bulk job by `workspaceId`. API access is denied when hosted-mode headers are missing or the role lacks the requested permission.

## SSO and 2FA

Provider strategy:

- Google Workspace: `DUDE_AUTH_GOOGLE_CLIENT_ID`, `DUDE_AUTH_GOOGLE_CLIENT_SECRET`
- Microsoft Entra ID: `DUDE_AUTH_MICROSOFT_CLIENT_ID`, `DUDE_AUTH_MICROSOFT_CLIENT_SECRET`
- Generic OIDC for self-host enterprise IdPs: `DUDE_AUTH_OIDC_ISSUER`, `DUDE_AUTH_OIDC_CLIENT_ID`, `DUDE_AUTH_OIDC_CLIENT_SECRET`
- Session signing: `DUDE_AUTH_SESSION_SECRET`

2FA policy is evaluated per workspace:

- `optional`: members can enroll voluntarily; admins are still enforceable by role.
- `required`: every active member must complete second factor before a session is accepted.
- Disabled members and unconfigured providers are blocked before session creation.

Secrets stay server-side in environment variables or the deployment secret manager. They are never stored in browser local storage.

## Verification

- `apps/web/src/lib/workspace.test.ts` covers role denial and cross-workspace data isolation.
- `apps/web/src/lib/auth-policy.ts` covers Google/Microsoft/OIDC/local provider allow-listing and 2FA failure paths.
- `packages/mcp-server/src/workspace/__tests__/access-control.test.ts` covers API self-host fallback, production fail-closed behavior, hosted header requirements, and role denial.
