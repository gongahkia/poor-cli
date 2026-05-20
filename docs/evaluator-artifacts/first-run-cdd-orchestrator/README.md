# First-Run CDD Orchestrator Artifact Pack

Observed on 2026-05-20 with:

```bash
npm run test:smoke:web
```

This pack is generated from the no-auth browser smoke fixture in `scripts/browser-smoke-web.mjs`. It demonstrates the first-run product path:

1. User searches `DBS BANK`.
2. The app resolves `DBS BANK LTD` / `03591300B`.
3. The web page calls `POST /api/v1/dude/cdd-orchestrator`.
4. Dude renders the cited CDD summary, Evidence Pack, Report Builder, and export flow.
5. The smoke exports a PDF report and structured JSON dossier with the export manifest.

## Fixture Boundary

This is fixture evidence, not a live public-source certification.

- No live ACRA, GeBIZ, TinyFish, OpenSanctions, OpenCorporates, adverse-media, or relationship-graph calls were made.
- Fixture source freshness is intentionally preserved in the artifacts: ACRA fixture observed at `2026-05-15T00:00:00.000Z`, upstream timestamp `2026-05-14`.
- The artifacts prove the no-auth orchestrated product envelope and browser export path, not the current state of DBS BANK LTD or any upstream registry.
- Live smoke and provider-specific checks still need to pass separately before release or hosted use.

## Artifacts

| File | Purpose |
| --- | --- |
| [first-run-artifact-manifest.json](./first-run-artifact-manifest.json) | Pack manifest with observed command, fixture/live boundary, source freshness, gaps, limits, provenance, and orchestrator stage trace. |
| [dude-cdd-report-03591300b-2026-05-20.pdf](./dude-cdd-report-03591300b-2026-05-20.pdf) | First-class PDF CDD report generated through the Report Builder export path. |
| [dude-diligence-03591300b.json](./dude-diligence-03591300b.json) | Structured dossier export containing citations, provenance, freshness, gaps, limits, source-use warnings, export manifest, and orchestrator metadata. |
| [web-smoke-success.png](./web-smoke-success.png) | Browser screenshot from the passing smoke flow. |

## Orchestrator Stages Preserved

The manifest and JSON export include these stages:

1. `acra_identity` - ACRA identity lookup completed.
2. `sector_inference` - sector inference completed from fixture SSIC evidence.
3. `official_modules` - ACRA and GeBIZ fixture modules completed, with GeBIZ no-match preserved as a gap.
4. `supplemental_review` - supplemental evidence path completed as analyst-review fixture data.
5. `ai_memo` - cited memo stage completed from fixture evidence.

Do not use this pack to bypass `npm run test:smoke:web`; it is a committed evaluator snapshot from one passing run.
