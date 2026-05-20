# Workspace Watchlists And Alerts

This is the current watchlist and alert boundary for local and hosted deployments. The web app's current workspace storage is browser-local `localStorage`; hosted durability requires a workspace backend.

## Current Boundary

Dude supports workspace-scoped watchlist records with module selection, notification-channel metadata, next-run timestamps, and manual alert checks. The local implementation records schedule metadata and "check now" alert history in the browser; hosted deployments can attach the same model to a worker and server-side store.

The old local shortlist surface has been removed from the product path; browser-local watchlists are now the lightweight local tracking surface.

## Local No-Account Path

1. Local watchlist export/import using structured JSON.
2. Manual refresh for selected watchlist entries through `/api/v1/dude/bulk-dossiers`.
3. Local change summaries computed from the previous exported snapshot and the refreshed dossier rows.
4. Optional one-shot reminder links that reopen the same browser workflow, without storing user data server-side.

## Workspace Account Path

Workspace alerts require:

- explicit user consent for stored counterparties,
- retention controls and deletion,
- per-source freshness and retry state,
- clear alert reasons tied to changed dossier evidence,
- rate limits that respect upstream public-data services.

## Non-Goals

- Silent background monitoring before a user opts in.
- Claims that missing data means a counterparty is clean.
- Legal, tax, credit, sanctions, or investment advice.
- Private ownership, director, shareholder, beneficial-owner, subsidiary, or control-graph inference.
