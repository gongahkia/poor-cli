# Signed export manifests

Dude attaches a local export manifest to dossier JSON, CSV, bulk JSON, bulk CSV, and PDF exports. The manifest is designed for downstream integrity checks and audit trails; it is not a third-party certificate or notarized signature.

## Manifest fields

- `schemaVersion`: currently `dude-export-manifest/v1`.
- `generatedAt`: ISO timestamp for the export operation.
- `toolVersion`: web export tool version.
- `dossierHash`: deterministic SHA-256 hash of the dossier payload.
- `sourceFreshness`: source-level observed timestamps copied from the dossier.
- `provenance`: source, tool, and record counts copied from the dossier.
- `includedArtifacts`: whether analyst memo or web-presence context was included.
- `signature`: deterministic SHA-256 signature over the manifest integrity payload.

## Verification

Use the web helper `verifyDossierExportManifest({ manifest, dossier })` from `apps/web/src/lib/export/manifest.ts` to recompute the dossier hash and compare it with the manifest. For JSON exports, the manifest and dossier are both embedded in the same file:

```ts
import { verifyDossierExportManifest } from "@/lib/export/manifest";

const valid = await verifyDossierExportManifest({
  dossier: exportedPayload.dossier,
  manifest: exportedPayload.manifest,
});
```

CSV and PDF exports include the manifest hash and signature for audit records. Keep the matching JSON export when a full payload-level verification path is required.

## Limits

The manifest confirms that an exported payload has not changed relative to the local hash calculation. It does not prove upstream truth, legal admissibility, analyst approval, or third-party attestation. Always read the dossier `freshness`, `gaps`, `limits`, and `provenance` fields alongside the manifest.
