import { Skeleton } from "@/components/ui/skeleton";
import { formatTimestamp } from "@/lib/dossier";
import type { AnalystMemoCitation, AnalystMemoReady, AnalystMemoResponse } from "@/types/analyst-memo";

export type AnalystMemoState =
  | { status: "loading" }
  | { status: "ready"; memo: AnalystMemoReady }
  | { status: "unavailable"; memo: Extract<AnalystMemoResponse, { status: "unavailable" }> }
  | { status: "error"; message: string; memo?: Extract<AnalystMemoResponse, { status: "error" }> };

const riskClassName: Record<AnalystMemoReady["riskRating"]["level"], string> = {
  high: "border-destructive/30 bg-destructive/5 text-destructive",
  medium: "border-border bg-muted/50 text-foreground",
  low: "border-border bg-card text-muted-foreground",
  unknown: "border-border bg-card text-muted-foreground",
};

const getSharedStateLabel = (value: string | null): string | null => {
  if (value === "ready") return "shared as memo generated";
  if (value === "unavailable") return "shared as memo unavailable";
  if (value === "error") return "shared after memo error";
  if (value === "pending") return "shared while memo was pending";
  return null;
};

function CitationBadges({ citationIds }: { citationIds: readonly string[] }) {
  if (citationIds.length === 0) return null;
  return (
    <span className="mt-2 flex flex-wrap gap-1">
      {citationIds.map((id) => (
        <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground" key={id}>
          {id}
        </span>
      ))}
    </span>
  );
}

function CitationList({ citations }: { citations: readonly AnalystMemoCitation[] }) {
  return (
    <div className="grid gap-2">
      {citations.map((citation) => (
        <article className="rounded-md border border-border p-3" key={citation.id}>
          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h4 className="text-sm font-medium text-foreground">{citation.label}</h4>
            <span className="font-mono text-xs text-muted-foreground">{citation.id}</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{citation.source}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{citation.text}</p>
        </article>
      ))}
    </div>
  );
}

export function AnalystMemoSection({
  sharedState,
  state,
}: {
  sharedState: string | null;
  state: AnalystMemoState;
}) {
  const sharedStateLabel = getSharedStateLabel(sharedState);

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-normal text-foreground">Analyst Memo</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            AI synthesis from cited dossier evidence.
          </p>
        </div>
        {sharedStateLabel === null ? null : (
          <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">{sharedStateLabel}</span>
        )}
      </div>

      {state.status === "loading" ? (
        <div className="mt-4 space-y-3">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      ) : state.status === "unavailable" ? (
        <div className="mt-4 rounded-md border border-border bg-muted/40 p-3">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h3 className="text-sm font-semibold text-foreground">Memo unavailable</h3>
            <span className="text-xs text-muted-foreground">{state.memo.provider} / {state.memo.model}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{state.memo.reason.message}</p>
        </div>
      ) : state.status === "error" ? (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3">
          <h3 className="text-sm font-semibold text-destructive">Memo failed</h3>
          <p className="mt-2 text-sm leading-6 text-destructive/90">
            {state.memo?.reason.message ?? state.message}
          </p>
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="rounded-md bg-muted px-2 py-1">{state.memo.provider}</span>
            <span className="rounded-md bg-muted px-2 py-1">{state.memo.model}</span>
            <span className="rounded-md bg-muted px-2 py-1">
              Generated: {formatTimestamp(state.memo.generatedAt) ?? state.memo.generatedAt}
            </span>
          </div>

          <div className="grid gap-3">
            {state.memo.evidenceMemo.length === 0 ? (
              <p className="text-sm text-muted-foreground">No cited memo claims were returned.</p>
            ) : state.memo.evidenceMemo.map((item) => (
              <article className="rounded-md border border-border p-3" key={item.text}>
                <p className="text-sm leading-6 text-foreground">{item.text}</p>
                <CitationBadges citationIds={item.citationIds} />
              </article>
            ))}
          </div>

          <article className={`rounded-md border p-3 ${riskClassName[state.memo.riskRating.level]}`}>
            <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
              <h3 className="text-sm font-semibold">Risk rating</h3>
              <span className="text-xs font-medium uppercase">{state.memo.riskRating.level}</span>
            </div>
            <p className="mt-2 text-sm leading-6">{state.memo.riskRating.rationale}</p>
            <CitationBadges citationIds={state.memo.riskRating.citationIds} />
          </article>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Decision aid</h3>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {state.memo.decisionAid.nextSteps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Confidence blockers</h3>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {state.memo.decisionAid.confidenceBlockers.map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
            </div>
          </div>

          <p className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
            {state.memo.decisionAid.nonAdvisoryReminder}
          </p>

          {state.memo.rejectedClaims.length === 0 ? null : (
            <div>
              <h3 className="text-sm font-semibold text-foreground">Rejected unsupported claims</h3>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {state.memo.rejectedClaims.map((claim) => (
                  <li key={claim.claim}>{claim.claim} - {claim.reason}</li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold text-foreground">Citations</h3>
            <div className="mt-2">
              <CitationList citations={state.memo.citations} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
