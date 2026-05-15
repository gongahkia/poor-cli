# Future Watchlists And Alerts

This is the planned path for watchlists without implementing accounts yet.

## Current Boundary

Dude currently supports local shortlist storage in the browser. That is intentionally not an account system, not cloud sync, and not a monitoring subscription.

## Future No-Account Path

1. Local watchlist export/import using the same structured JSON shape as shortlist export.
2. Manual refresh for selected shortlist entries through `/api/v1/dude/bulk-dossiers`.
3. Local change summaries computed from the previous exported snapshot and the refreshed dossier rows.
4. Optional one-shot reminder links that reopen the same browser workflow, without storing user data server-side.

## Future Account Path

Accounts should be considered only after the public no-account workflow proves useful. Account-based alerts would need:

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
