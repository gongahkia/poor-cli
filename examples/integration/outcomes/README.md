# CDD Outcome Integration Examples

Runnable scripts that mirror the retained CDD outcome briefs. Use these after `examples/integration/basic-client.{ts,py}` when you want to see how a dossier becomes UI-ready output with `riskFlags`, `nextChecks`, gaps, provenance, and report evidence.

## Prerequisites

```bash
npm install
npm run build
```

The retained CDD scripts use public registry and GeBIZ surfaces by default. Optional external diligence providers can be configured separately when needed.

## Scripts

| Script | Outcome | Run |
|---|---|---|
| `sme-diligence-dashboard.ts` | Business dossier + GeBIZ tender follow-up | `npx tsx examples/integration/outcomes/sme-diligence-dashboard.ts "DP ARCHITECTS PTE LTD"` |
| `procurement-monitor.ts` | GeBIZ tender evidence for procurement review | `npx tsx examples/integration/outcomes/procurement-monitor.ts construction` |
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
