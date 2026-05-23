# Pulse Outcome Integration Examples

Runnable scripts that show how Swee Pulse and Swee Shield payloads become UI-ready output with signals, source health, gaps, and audit rows.

## Prerequisites

```bash
npm install
npm run build
```

## Scripts

| Script | Outcome | Run |
|---|---|---|
| `city-ops-dashboard.ts` | Pulse snapshot + Shield audit follow-up | `npx tsx examples/integration/outcomes/city-ops-dashboard.ts Bedok` |
| `procurement-monitor.ts` | Direct GeBIZ source-adapter lookup for a keyword | `npx tsx examples/integration/outcomes/procurement-monitor.ts construction` |
| `city_ops_dashboard.py` | Same Pulse/Shield dashboard pattern in Python | `python3 examples/integration/outcomes/city_ops_dashboard.py Bedok` |

## What These Demonstrate

- Reading `structuredContent` in both Node and Python clients.
- Rendering `signals`, `sourceHealth`, and `gaps` in a compact operator view.
- Keeping raw source-adapter calls separate from the app-level Pulse path.
- Using Shield audit rows as the follow-up surface for policy and replay metadata.

## Boundaries

These scripts are integration patterns, not official operational instructions. They never rewrite source freshness, hide gaps, or turn missing public-data evidence into a positive clearance claim.
