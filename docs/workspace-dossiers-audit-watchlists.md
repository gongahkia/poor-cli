# Workspace Dossiers, Audit Log, Watchlists, and Bulk Jobs

This is the implementation contract for issues #45, #47, #48, and #49.

The current web implementation stores this workspace model in browser `localStorage` under the active browser profile. That is suitable for local prototype and self-contained analyst review, but it is not durable hosted workspace storage or immutable server-side audit retention.

## Persisted Dossiers

Single counterparty pages auto-save a workspace dossier record with:

- dossier envelope, records, provenance, freshness, gaps, and limits
- analyst memo state when available
- web-presence metadata when available
- folder id, actor id, created/updated timestamps

The workspace UI at `/workspace` provides dossier search, folder filtering, and links back to the canonical counterparty page. In the current web build, those records remain browser-local unless exported.

## Audit Events

Audit events are append-only within the browser-local store with:

- `eventType`: search, dossier generation, memo generation, export, watchlist change, or bulk run
- actor, role, workspace id, request id
- input fingerprint and output hash
- provenance/freshness metadata
- arbitrary structured metadata for event-specific context

The workspace page exposes event-type filtering. The REST gateway also enforces workspace permissions for memo, bulk, debug logs, and direct tool calls. Hosted deployments need a server-side audit store before describing these events as durable retention evidence.

## Watchlists

Watchlist items are workspace-scoped and store:

- identifier and display label
- module set: ACRA, GeBIZ, BCA, BOA, CEA, HSA, HLB
- notification channel: in-app, email, or webhook
- next scheduled run timestamp and alert history

The current local implementation records schedule metadata and a manual "check now" alert. Hosted deployments can attach the same model to a worker that reruns the module inputs and appends alert records when evidence, gaps, or risk flags change.

## Bulk Jobs

Bulk diligence now supports 200 rows per browser-local workspace job. The UI records:

- requested/executed row counts
- risk summary grid
- gap and upstream-failure totals
- partial-failure status
- retry for failed/upstream-failed rows
- export audit events

Backend parsing enforces the same 200-row cap so UI and API behavior match.
