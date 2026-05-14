import { formatTimestamp } from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

function getVerifiedAt(dossier: BusinessDossier, source: string): string {
  const normalizedSource = source.toLowerCase();
  const freshness = dossier.freshness.find((item) =>
    item.source.toLowerCase().includes(normalizedSource),
  );
  return formatTimestamp(freshness?.observedAt) ?? "Not available";
}

function getUpstreamTimestamp(dossier: BusinessDossier, source: string): string | null {
  const normalizedSource = source.toLowerCase();
  const freshness = dossier.freshness.find((item) =>
    item.source.toLowerCase().includes(normalizedSource),
  );
  return formatTimestamp(freshness?.upstreamTimestamp ?? null);
}

export function ProvenanceSection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Provenance</h2>
      <div className="mt-4 grid gap-3">
        {dossier.provenance.map((item) => {
          const upstreamTimestamp = getUpstreamTimestamp(dossier, item.source);

          return (
            <article className="rounded-md border border-border p-3" key={`${item.source}-${item.tool}`}>
              <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <h3 className="font-medium text-foreground">{item.source}</h3>
                <p className="text-xs text-muted-foreground">
                  Last verified: {getVerifiedAt(dossier, item.source)}
                </p>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.coverage}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-md bg-muted px-2 py-1">{item.tool}</span>
                <span className="rounded-md bg-muted px-2 py-1">{item.recordCount} records</span>
                <span className="rounded-md bg-muted px-2 py-1">
                  {item.authRequired ? "Auth required" : "No auth"}
                </span>
                {upstreamTimestamp !== null ? (
                  <span className="rounded-md bg-muted px-2 py-1">Source timestamp: {upstreamTimestamp}</span>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
