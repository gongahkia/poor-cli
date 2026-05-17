import { ExternalLink, MapPin } from "lucide-react";

import {
  buildDiligenceSnapshot,
  formatRecordValue,
  getDossierConfidence,
  getSectorBadges,
} from "@/lib/dossier";
import { cn } from "@/lib/utils";
import type { BusinessDossier } from "@/types/dossier";

const buildMapQuery = (address: string, entityName: string | null): string =>
  [entityName, address].filter((part): part is string => part !== null && part.trim() !== "").join(", ");

const buildGoogleMapsEmbedUrl = (query: string): string =>
  `https://www.google.com/maps?q=${encodeURIComponent(query)}&output=embed`;

const buildGoogleMapsSearchUrl = (query: string): string =>
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;

const confidencePillClassName = (score: number | undefined, level: string): string => {
  const normalizedLevel = level.toLowerCase();
  if (score !== undefined) {
    if (score >= 0.8) {
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    }
    if (score >= 0.55) {
      return "border-amber-200 bg-amber-50 text-amber-800";
    }
    return "border-rose-200 bg-rose-50 text-rose-800";
  }
  if (normalizedLevel === "high") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (normalizedLevel === "medium") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  if (normalizedLevel === "low") {
    return "border-rose-200 bg-rose-50 text-rose-800";
  }
  return "border-border bg-muted text-muted-foreground";
};

const formatConfidencePill = (level: string, score: number | undefined): string =>
  `Confidence: ${level}${score === undefined ? "" : ` (${Math.round(score * 100)}%)`}`;

export function SnapshotSection({ dossier }: { dossier: BusinessDossier }) {
  const snapshot = buildDiligenceSnapshot(dossier);
  const confidence = getDossierConfidence(dossier);
  const sectors = getSectorBadges(dossier);
  const mapQuery = snapshot.address === null ? null : buildMapQuery(snapshot.address, snapshot.entityName);
  const rows = [
    ["Status", snapshot.status],
    ["UEN", snapshot.uen],
    ["Entity type", snapshot.entityType],
    ["Entity age", snapshot.age],
    ["Address", snapshot.address],
    ["Primary SSIC", snapshot.primarySsic],
    ["Matched modules", snapshot.matchedModules],
  ] as const;

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-6">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-normal text-foreground">Diligence Snapshot</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            A compact readout from the official registry evidence returned for this search.
          </p>
        </div>
        {sectors.length > 0 || confidence !== null ? (
          <div className="flex min-w-0 flex-wrap gap-2 sm:justify-end">
            {confidence === null ? null : (
              <span
                className={cn(
                  "max-w-full break-words rounded-full border px-2.5 py-1 text-xs font-medium",
                  confidencePillClassName(confidence.score, confidence.level),
                )}
              >
                {formatConfidencePill(confidence.level, confidence.score)}
              </span>
            )}
            {sectors.map((sector) => (
              <span className="max-w-full break-words rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground" key={sector}>
                {sector}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-[repeat(2,minmax(0,1fr))]">
        {rows.map(([label, value]) => (
          <div className="min-w-0 rounded-md border border-border p-3" key={label}>
            <dt className="text-xs font-medium uppercase text-muted-foreground">{label}</dt>
            <dd className="mt-1 break-words text-sm leading-6 text-foreground">
              {formatRecordValue(label, value)}
            </dd>
          </div>
        ))}
      </dl>

      {mapQuery === null ? null : (
        <div className="mt-6 border-t border-border pt-5">
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <MapPin aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-base font-semibold text-foreground">Location</h3>
              </div>
              <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{snapshot.address}</p>
            </div>
            <a
              className="inline-flex w-fit shrink-0 items-center gap-1 text-sm font-medium text-foreground underline-offset-4 hover:underline"
              href={buildGoogleMapsSearchUrl(mapQuery)}
              rel="noreferrer"
              target="_blank"
            >
              Open map
              <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
            </a>
          </div>
          <div className="mt-4 aspect-[16/9] w-full overflow-hidden rounded-md border border-border bg-muted sm:aspect-[21/8]">
            <iframe
              className="h-full w-full"
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              src={buildGoogleMapsEmbedUrl(mapQuery)}
              title={`Map for ${snapshot.entityName ?? "organisation location"}`}
            />
          </div>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Map is based on the address returned in the dossier; confirm exact premises before site visits or outreach.
          </p>
        </div>
      )}
    </section>
  );
}
