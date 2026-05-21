import {
  buildSupplementalEvidenceReviewItems,
  outcomeStateLabel,
  providerStateLabel,
  supplementalEvidenceCaveat,
  type SupplementalEvidenceReviewItem,
  type SupplementalProviderState,
} from "@/lib/supplemental-evidence";
import { cn } from "@/lib/utils";
import type { PeopleDiscovery } from "@/lib/api/client";
import type { BusinessDossier } from "@/types/dossier";
import type { WebPresence } from "@/lib/api/client";

type SupplementalEvidencePanelProps = {
  dossier: BusinessDossier;
  peopleDiscovery?: PeopleDiscovery;
  webPresence?: WebPresence;
};

const stateClassName: Record<SupplementalProviderState, string> = {
  configured: "border-emerald-200 bg-emerald-50 text-emerald-900",
  error: "border-destructive/30 bg-destructive/5 text-destructive",
  rate_limited: "border-amber-200 bg-amber-50 text-amber-900",
  unconfigured: "border-border bg-muted/50 text-muted-foreground",
};

function EvidenceLabels({ labels }: { labels: readonly string[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {Array.from(new Set(labels)).map((label) => (
        <span className="rounded-md border border-border bg-background px-2 py-1 text-xs text-muted-foreground" key={label}>
          {label}
        </span>
      ))}
    </div>
  );
}

function SupplementalItemCard({ item }: { item: SupplementalEvidenceReviewItem }) {
  return (
    <article className="min-w-0 rounded-lg border border-border bg-card p-3 shadow-sm sm:p-4">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h4 className="break-words font-semibold text-foreground">{item.title}</h4>
          <p className="mt-1 break-words text-xs text-muted-foreground">
            {item.provider} / {item.tool}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5">
          <span className={cn("w-fit rounded-md border px-2 py-0.5 text-xs font-medium", stateClassName[item.providerState])}>
            {providerStateLabel(item.providerState)}
          </span>
          <span className="w-fit rounded-md border border-border bg-muted/50 px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {outcomeStateLabel(item.outcome)}
          </span>
        </div>
      </div>
      <EvidenceLabels labels={item.evidenceLabels} />
      <dl className="mt-3 grid gap-3 text-sm lg:grid-cols-3">
        <div className="min-w-0">
          <dt className="text-xs font-semibold uppercase text-muted-foreground">Confidence</dt>
          <dd className="mt-1 break-words leading-6 text-foreground">{item.confidenceLabel}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs font-semibold uppercase text-muted-foreground">Limitation</dt>
          <dd className="mt-1 break-words leading-6 text-muted-foreground">{item.limitationLabel}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs font-semibold uppercase text-muted-foreground">Records</dt>
          <dd className="mt-1 break-words leading-6 text-muted-foreground">{item.recordCount}</dd>
        </div>
      </dl>
      <p className="mt-3 rounded-md bg-muted/50 p-2 text-xs leading-5 text-muted-foreground">
        {item.caveat}
      </p>
      {item.sourceUseWarning === null ? null : (
        <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs leading-5 text-amber-900">
          {item.sourceUseWarning}
        </p>
      )}
      {item.gaps.length === 0 && item.limits.length === 0 ? null : (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Gaps and limits</summary>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground">
            {[...item.gaps, ...item.limits].map((entry, index) => (
              <li className="break-words" key={`${item.id}-${index}`}>{entry}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

export function SupplementalEvidencePanel({
  dossier,
  peopleDiscovery,
  webPresence,
}: SupplementalEvidencePanelProps) {
  const items = buildSupplementalEvidenceReviewItems({ dossier, peopleDiscovery, webPresence });

  if (items.length === 0) return null;

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-muted-foreground">Supplemental evidence</p>
          <h2 className="mt-1 text-xl font-semibold tracking-normal text-foreground">Analyst-review checks</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {supplementalEvidenceCaveat}
          </p>
        </div>
        <span className="w-fit rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
          {items.length} checks
        </span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-[repeat(2,minmax(0,1fr))]">
        {items.map((item) => <SupplementalItemCard item={item} key={item.id} />)}
      </div>
    </section>
  );
}
