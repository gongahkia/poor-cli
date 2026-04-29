# Outcome Integration Examples

Runnable scripts that mirror the outcome briefs under `examples/outcome-*.md`. Use these as the next step after `examples/integration/basic-client.{ts,py}` when you want to see end-to-end how a brief becomes UI-ready output, including `riskFlags`, `nextChecks`, and partial-failure recovery.

## Prerequisites

```bash
npm install
npm run build
```

For credentialed flows (property brief, transport brief, OneMap-backed lookups), set:

```bash
export SG_API_ONEMAP_EMAIL=...
export SG_API_ONEMAP_PASSWORD=...
export SG_API_URA_KEY=...
export SG_API_LTA_KEY=...
```

## Scripts

| Script | Outcome | Run |
|---|---|---|
| `relocation-assistant.ts` | Property + civic + transport + environment briefing | `npx tsx examples/integration/outcomes/relocation-assistant.ts 460123` |
| `school-childcare-finder.ts` | MOE schools + ECDA childcare around an address | `npx tsx examples/integration/outcomes/school-childcare-finder.ts 560123` |
| `sme-diligence-dashboard.ts` | Business dossier + GeBIZ tender follow-up | `npx tsx examples/integration/outcomes/sme-diligence-dashboard.ts "DP ARCHITECTS PTE LTD"` |
| `procurement-monitor.ts` | GeBIZ tender + gov-feed correlation | `npx tsx examples/integration/outcomes/procurement-monitor.ts construction` |
| `outdoor-event-checker.ts` | Environment + transport go/hold/cancel verdict | `npx tsx examples/integration/outcomes/outdoor-event-checker.ts Bedok` |
| `sme_diligence_dashboard.py` | Same as TS, but in Python with a job-runner pattern | `python3 examples/integration/outcomes/sme_diligence_dashboard.py "DP ARCHITECTS PTE LTD"` |

## What These Demonstrate

- Reading `record` out of `structuredContent` in both Node and Python clients.
- Rendering `summary`, `riskFlags`, `gaps`, `nextChecks`, and freshness in a compact UI-friendly form.
- Backend job patterns: per-target try/except, queue-style iteration, structured outcome records ready for persistence or alerting.
- Partial-failure handling: when a sub-source fails, the brief still returns and the script surfaces the gap rather than crashing.

## Boundaries

These scripts are integration patterns, not products. They never:

- treat a brief as a recommendation engine,
- silently retry past `gaps[]`,
- rewrite freshness or provenance for nicer output,
- persist credentials anywhere outside env vars / the keystore.
