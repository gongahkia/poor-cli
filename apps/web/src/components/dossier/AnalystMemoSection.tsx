import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  FileText,
  ListChecks,
  ShieldAlert,
} from "lucide-react";

import type { AgentPlanTask } from "@/components/ui/agent-plan";
import { AgentPlan } from "@/components/ui/agent-plan-loader";
import { formatLabel, formatTimestamp } from "@/lib/dossier";
import { cn } from "@/lib/utils";
import type { AnalystMemoCitation, AnalystMemoReady, AnalystMemoResponse } from "@/types/analyst-memo";

export type AnalystMemoState =
  | { status: "loading" }
  | { status: "ready"; memo: AnalystMemoReady }
  | { status: "unavailable"; memo: Extract<AnalystMemoResponse, { status: "unavailable" }> }
  | { status: "error"; message: string; memo?: Extract<AnalystMemoResponse, { status: "error" }> };

const riskClassName: Record<AnalystMemoReady["riskRating"]["level"], string> = {
  high: "border-destructive/30 bg-destructive/5 text-destructive",
  medium: "border-amber-200 bg-amber-50 text-amber-900",
  low: "border-emerald-200 bg-emerald-50 text-emerald-900",
  unknown: "border-border bg-muted/40 text-muted-foreground",
};

const riskPillClassName: Record<AnalystMemoReady["riskRating"]["level"], string> = {
  high: "border-destructive/30 bg-background text-destructive",
  medium: "border-amber-200 bg-background text-amber-900",
  low: "border-emerald-200 bg-background text-emerald-900",
  unknown: "border-border bg-background text-muted-foreground",
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
    <span className="flex min-w-0 flex-wrap gap-1.5">
      {citationIds.map((id) => (
        <span
          className="max-w-full break-all rounded-full border border-border bg-muted/60 px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
          key={id}
          title="Citation reference"
        >
          {id}
        </span>
      ))}
    </span>
  );
}

function CitationTags({ citationIds }: { citationIds: readonly string[] }) {
  if (citationIds.length === 0) return null;
  return (
    <div className="mt-3 flex min-w-0 items-center gap-2">
      <span className="text-xs font-medium uppercase text-muted-foreground">Sources</span>
      <CitationBadges citationIds={citationIds} />
    </div>
  );
}

function formatCitationTitle(label: string): string {
  const trimmed = label.trim();
  if (trimmed === "") return "Evidence";
  if (/^[A-Z0-9_\-\s]+$/.test(trimmed) && /[_-]/.test(trimmed)) {
    return formatLabel(trimmed.toLowerCase());
  }
  return formatLabel(trimmed);
}

function CitationList({ citations }: { citations: readonly AnalystMemoCitation[] }) {
  return (
    <div className="mt-3 grid gap-2">
      {citations.map((citation) => (
        <article className="min-w-0 rounded-md border border-border bg-background p-3" key={citation.id}>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="min-w-0 break-words text-sm font-semibold text-foreground">
                {formatCitationTitle(citation.label)}
              </h4>
              <p className="mt-1 break-words text-xs text-muted-foreground">{citation.source}</p>
            </div>
            <span className="w-fit shrink-0 rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {citation.id}
            </span>
          </div>
          <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{citation.text}</p>
        </article>
      ))}
    </div>
  );
}

function MemoMetadata({ memo }: { memo: AnalystMemoReady }) {
  return (
    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1">
        <FileText aria-hidden="true" className="h-3.5 w-3.5" />
        {memo.provider} / {memo.model}
      </span>
      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1">
        <CalendarClock aria-hidden="true" className="h-3.5 w-3.5" />
        {formatTimestamp(memo.generatedAt) ?? memo.generatedAt}
      </span>
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
  const loadingTasks: AgentPlanTask[] = [
    {
      id: "memo-context",
      title: "Collect memo context",
      description: "Read dossier evidence, freshness, gaps, limits, and optional web discovery results.",
      status: "completed",
      priority: "high",
      subtasks: [
        {
          id: "dossier-evidence",
          title: "Load cited dossier evidence",
          description: "Gather official registry evidence and source limits before asking for synthesis.",
          status: "completed",
          priority: "high",
          tools: ["sg_business_dossier"],
        },
      ],
    },
    {
      id: "memo-synthesis",
      title: "Draft analyst memo",
      description: "Ask the configured memo provider to synthesize only from cited evidence.",
      status: "in-progress",
      priority: "high",
      subtasks: [
        {
          id: "memo-call",
          title: "Call memo endpoint",
          description: "Generating evidence notes, risk rating, next steps, and confidence blockers.",
          status: "in-progress",
          priority: "high",
          tools: ["dude memo"],
        },
        {
          id: "citation-check",
          title: "Check citation structure",
          description: "Ensure returned claims keep citation IDs and non-advisory reminders attached.",
          status: "pending",
          priority: "high",
          tools: ["dude-web"],
        },
      ],
    },
  ];

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-normal text-foreground">Analyst Memo</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            AI synthesis from cited dossier evidence.
          </p>
        </div>
        {sharedStateLabel === null ? null : (
          <span className="w-fit shrink-0 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">{sharedStateLabel}</span>
        )}
      </div>

      {state.status === "loading" ? (
        <AgentPlan
          className="mt-4"
          description="Dude is synthesizing a memo from cited dossier evidence."
          tasks={loadingTasks}
          title="Dude is drafting the memo"
        />
      ) : state.status === "unavailable" ? (
        <div className="mt-4 min-w-0 rounded-md border border-border bg-muted/40 p-3">
          <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h3 className="text-sm font-semibold text-foreground">Memo unavailable</h3>
            <span className="break-all text-xs text-muted-foreground">{state.memo.provider} / {state.memo.model}</span>
          </div>
          <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{state.memo.reason.message}</p>
        </div>
      ) : state.status === "error" ? (
        <div className="mt-4 min-w-0 rounded-md border border-destructive/30 bg-destructive/5 p-3">
          <h3 className="text-sm font-semibold text-destructive">Memo failed</h3>
          <p className="mt-2 break-words text-sm leading-6 text-destructive/90">
            {state.memo?.reason.message ?? state.message}
          </p>
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          <MemoMetadata memo={state.memo} />

          <div className="min-w-0 rounded-md border border-border bg-background p-4">
            <div className="flex items-center gap-2">
              <FileText aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Evidence-backed findings</h3>
            </div>
            {state.memo.evidenceMemo.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">No cited memo claims were returned.</p>
            ) : (
              <ol className="mt-4 space-y-4">
                {state.memo.evidenceMemo.map((item, index) => (
                  <li className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-3" key={item.text}>
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="break-words text-sm leading-6 text-foreground">{item.text}</p>
                      <CitationTags citationIds={item.citationIds} />
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>

          <article className={cn("min-w-0 rounded-md border p-4", riskClassName[state.memo.riskRating.level])}>
            <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 gap-3">
                <ShieldAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold">Risk rating</h3>
                  <p className="mt-2 break-words text-sm leading-6">{state.memo.riskRating.rationale}</p>
                </div>
              </div>
              <span className={cn(
                "w-fit shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold uppercase",
                riskPillClassName[state.memo.riskRating.level],
              )}>
                {state.memo.riskRating.level}
              </span>
            </div>
            <CitationTags citationIds={state.memo.riskRating.citationIds} />
          </article>

          <div className="grid gap-4 md:grid-cols-[repeat(2,minmax(0,1fr))]">
            <div className="min-w-0 rounded-md border border-border bg-background p-4">
              <div className="flex items-center gap-2">
                <ListChecks aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Action checklist</h3>
              </div>
              <ul className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                {state.memo.decisionAid.nextSteps.map((step, index) => (
                  <li className="grid min-w-0 grid-cols-[1.5rem_minmax(0,1fr)] gap-2" key={step}>
                    <span className="mt-1 flex h-5 w-5 items-center justify-center rounded-full border border-border text-[11px] font-medium text-muted-foreground">
                      {index + 1}
                    </span>
                    <span className="break-words">{step}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="min-w-0 rounded-md border border-border bg-background p-4">
              <div className="flex items-center gap-2">
                <CircleAlert aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Confidence blockers</h3>
              </div>
              <ul className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                {state.memo.decisionAid.confidenceBlockers.map((blocker) => (
                  <li className="flex min-w-0 gap-2" key={blocker}>
                    <AlertTriangle aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="break-words">{blocker}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <p className="inline-flex min-w-0 items-start gap-2 break-words rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
            <CheckCircle2 aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {state.memo.decisionAid.nonAdvisoryReminder}
          </p>

          {state.memo.rejectedClaims.length === 0 ? null : (
            <div>
              <h3 className="text-sm font-semibold text-foreground">Rejected unsupported claims</h3>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {state.memo.rejectedClaims.map((claim) => (
                  <li className="break-words" key={claim.claim}>{claim.claim} - {claim.reason}</li>
                ))}
              </ul>
            </div>
          )}

          <details className="min-w-0 rounded-md border border-border bg-muted/20 p-3">
            <summary className="cursor-pointer text-sm font-semibold text-foreground">
              Evidence references ({state.memo.citations.length})
            </summary>
            <div>
              <CitationList citations={state.memo.citations} />
            </div>
          </details>
        </div>
      )}
    </section>
  );
}
