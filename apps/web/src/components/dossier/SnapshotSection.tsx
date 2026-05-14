import {
  buildDiligenceSnapshot,
  formatRecordValue,
  getSectorBadges,
} from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

export function SnapshotSection({ dossier }: { dossier: BusinessDossier }) {
  const snapshot = buildDiligenceSnapshot(dossier);
  const sectors = getSectorBadges(dossier);
  const rows = [
    ["Status", snapshot.status],
    ["UEN", snapshot.uen],
    ["Entity type", snapshot.entityType],
    ["Entity age", snapshot.age],
    ["Address", snapshot.address],
    ["Primary SSIC", snapshot.primarySsic],
    ["Matched modules", snapshot.matchedModules],
    ["Confidence", snapshot.confidence],
  ] as const;

  return (
    <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-normal text-foreground">Diligence Snapshot</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            A compact readout from the official registry evidence returned for this search.
          </p>
        </div>
        {sectors.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {sectors.map((sector) => (
              <span className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground" key={sector}>
                {sector}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div className="rounded-md border border-border p-3" key={label}>
            <dt className="text-xs font-medium uppercase text-muted-foreground">{label}</dt>
            <dd className="mt-1 text-sm leading-6 text-foreground">
              {formatRecordValue(label, value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
