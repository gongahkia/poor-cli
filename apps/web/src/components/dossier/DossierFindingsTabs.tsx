import {
  Check,
  ClipboardCheck,
  Copy,
  Database,
  FileSearch,
  FileQuestion,
  LayoutDashboard,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from "react";

import { AnalystMemoSection, type AnalystMemoState } from "@/components/dossier/AnalystMemoSection";
import { ConfidenceSection } from "@/components/dossier/ConfidenceSection";
import { EvidenceSection, type ModuleFollowUpRequest, type RunningBusinessModule } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import { HandoffSection } from "@/components/dossier/HandoffSection";
import { NextChecksSection } from "@/components/dossier/NextChecksSection";
import { PdpaChecklistSection } from "@/components/dossier/PdpaChecklistSection";
import { PeopleDiscoverySection, type PeopleDiscoveryState } from "@/components/dossier/PeopleDiscoverySection";
import { ProvenanceSection } from "@/components/dossier/ProvenanceSection";
import { RiskSection } from "@/components/dossier/RiskSection";
import { SnapshotSection } from "@/components/dossier/SnapshotSection";
import { WebPresenceSection, type WebPresenceState } from "@/components/dossier/WebPresenceSection";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { postGatewayJson } from "@/lib/api/client";
import {
  buildDiligenceSnapshot,
  formatRecordValue,
  formatTimestamp,
  getDossierConfidence,
  getDossierRecordGroups,
  getSummaryString,
  riskCodeLabel,
} from "@/lib/dossier";
import { buildFallbackInteractiveSummary } from "@/lib/interactive-summary";
import { buildPdpaChecklist } from "@/lib/pdpa";
import { cn } from "@/lib/utils";
import type { BusinessDossier } from "@/types/dossier";
import type {
  InteractiveSummaryPrompt,
  InteractiveSummaryResponse,
  InteractiveSummarySegment,
  SummaryTargetId,
} from "@/types/interactive-summary";

type DossierFindingsTabsProps = {
  dossier: BusinessDossier;
  isPdpaExporting: boolean;
  memoState: AnalystMemoState;
  onExportPdpaReport: (reviewedItemIds: readonly string[]) => void;
  onModuleFollowUp: (request: ModuleFollowUpRequest) => void;
  peopleDiscoveryState: PeopleDiscoveryState;
  rerunningModule: RunningBusinessModule;
  sharedMemoState: string | null;
  webPresenceState: WebPresenceState;
};

type FindingsTab = {
  count: number;
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: FindingsTabValue;
};

type FindingsTabValue = "summary" | "overview" | "evidence" | "actions" | "audit" | "missing";

type InteractiveSummaryState =
  | { status: "loading" }
  | { status: "ready"; summary: Extract<InteractiveSummaryResponse, { status: "ready" }> }
  | { status: "fallback"; generatedAt: string; prompt?: InteractiveSummaryPrompt; reason: string; segments: InteractiveSummarySegment[] }
  | { status: "unavailable"; summary: Extract<InteractiveSummaryResponse, { status: "unavailable" }> }
  | { status: "error"; message: string; summary?: Extract<InteractiveSummaryResponse, { status: "error" }> };

type SummaryTargetConfig = {
  elementId: string;
  label: string;
  tab: FindingsTabValue;
};

type SummaryTargetPreview = {
  body: string;
  meta: string;
  title: string;
};

const summaryTargetConfig: Record<SummaryTargetId, SummaryTargetConfig> = {
  "actions.nextChecks": { elementId: "dossier-actions-next-checks", label: "Next checks", tab: "actions" },
  "actions.pdpa": { elementId: "dossier-actions-pdpa", label: "PDPA checklist", tab: "actions" },
  "audit.gaps": { elementId: "dossier-missing-gaps", label: "Missing evidence", tab: "missing" },
  "audit.handoff": { elementId: "dossier-audit-handoff", label: "Agent handoff", tab: "audit" },
  "audit.provenance": { elementId: "dossier-audit-provenance", label: "Provenance", tab: "audit" },
  "evidence.metrics": { elementId: "dossier-evidence-metrics", label: "Evidence metrics", tab: "evidence" },
  "evidence.notSearched": { elementId: "dossier-evidence-not-searched", label: "Not searched modules", tab: "evidence" },
  "evidence.peopleDiscovery": { elementId: "dossier-evidence-people", label: "People discovery", tab: "evidence" },
  "evidence.records": { elementId: "dossier-evidence-records", label: "Matched records", tab: "evidence" },
  "evidence.searched": { elementId: "dossier-evidence-searched", label: "Searched modules", tab: "evidence" },
  "evidence.webPresence": { elementId: "dossier-evidence-web", label: "Web presence", tab: "evidence" },
  "overview.confidence": { elementId: "dossier-overview-confidence", label: "Confidence", tab: "overview" },
  "overview.memo": { elementId: "dossier-overview-memo", label: "Analyst memo", tab: "overview" },
  "overview.risk": { elementId: "dossier-overview-risk", label: "Risk signals", tab: "overview" },
  "overview.snapshot": { elementId: "dossier-overview-snapshot", label: "Diligence snapshot", tab: "overview" },
  "overview.summary": { elementId: "dossier-overview-summary", label: "Registry summary", tab: "overview" },
};

function tabCountLabel(count: number): string {
  return count > 99 ? "99+" : String(count);
}

function SummarySection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-6">
      <h2 className="text-base font-semibold text-foreground">Registry Summary</h2>
      <dl className="mt-4 grid gap-3 sm:grid-cols-[repeat(2,minmax(0,1fr))]">
        {dossier.summary.map((item) => (
          <div key={`${item.label}-${item.source ?? ""}`} className="min-w-0 rounded-md border border-border p-3">
            <dt className="text-xs font-medium uppercase text-muted-foreground">{item.label}</dt>
            <dd className="mt-1 break-words text-sm text-foreground">
              {item.value === null || item.value === undefined || item.value === "" ? "-" : String(item.value)}
            </dd>
            {item.source !== undefined && item.source !== null ? (
              <dd className="mt-1 text-xs text-muted-foreground">Source: {item.source}</dd>
            ) : null}
          </div>
        ))}
      </dl>
    </section>
  );
}

function SectionAnchor({
  children,
  id,
}: {
  children: ReactNode;
  id: string;
}) {
  return (
    <div className="scroll-mt-6 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70" id={id} tabIndex={-1}>
      {children}
    </div>
  );
}

function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

function joinOrNone(values: readonly string[] | undefined): string {
  return values === undefined || values.length === 0 ? "none" : values.join(", ");
}

function buildSummaryTargetPreview(
  dossier: BusinessDossier,
  targetId: SummaryTargetId,
): SummaryTargetPreview {
  const target = summaryTargetConfig[targetId];
  const resolution = dossier.records.resolution;
  const snapshot = buildDiligenceSnapshot(dossier);
  const confidence = getDossierConfidence(dossier);
  const recordGroups = getDossierRecordGroups(dossier);
  const recordCount = recordGroups.reduce(
    (sum, group) => sum + group.tables.reduce((tableSum, table) => tableSum + table.records.length, 0),
    0,
  );
  const searchedModules = resolution?.searchedModules ?? [];
  const matchedModules = resolution?.matchedModules ?? [];
  const unsearchedModules = resolution?.unsearchedModules ?? [];

  if (targetId === "overview.summary") {
    const entity = getSummaryString(dossier, "Entity") ?? dossier.title;
    const uen = getSummaryString(dossier, "UEN") ?? "UEN not returned";
    const status = getSummaryString(dossier, "Entity status") ?? "status not returned";
    return {
      body: `${entity} - ${uen} - ${status}.`,
      meta: "Registry summary",
      title: target.label,
    };
  }

  if (targetId === "overview.snapshot") {
    return {
      body: [
        snapshot.status === null ? null : `Status: ${snapshot.status}`,
        snapshot.primarySsic === null ? null : `Primary SSIC: ${snapshot.primarySsic}`,
        snapshot.address === null ? null : `Address: ${snapshot.address}`,
      ].filter(Boolean).join(". ") || "Snapshot fields were not returned.",
      meta: "Diligence snapshot",
      title: target.label,
    };
  }

  if (targetId === "overview.risk") {
    const flags = dossier.riskFlags ?? [];
    return {
      body: flags.length === 0
        ? "No risk flags were returned by the selected modules."
        : flags.slice(0, 2).map((flag) => `${riskCodeLabel(flag.code)}: ${flag.message}`).join(" "),
      meta: formatCount(flags.length, "risk signal"),
      title: target.label,
    };
  }

  if (targetId === "overview.confidence") {
    return {
      body: confidence === null
        ? "No dossier confidence block was returned."
        : `${confidence.level}${confidence.score === undefined ? "" : ` (${Math.round(confidence.score * 100)}%)`}${confidence.rationale === undefined ? "" : ` - ${confidence.rationale}`}`,
      meta: "Match confidence",
      title: target.label,
    };
  }

  if (targetId === "evidence.metrics") {
    return {
      body: dossier.evidence.slice(0, 4).map((item) => `${item.label}: ${formatRecordValue(item.label, item.value)}`).join("; "),
      meta: formatCount(dossier.evidence.length, "metric"),
      title: target.label,
    };
  }

  if (targetId === "evidence.records") {
    return {
      body: `${formatCount(recordCount, "matched record")} across matched modules: ${joinOrNone(matchedModules)}.`,
      meta: "Public registry records",
      title: target.label,
    };
  }

  if (targetId === "evidence.searched") {
    return {
      body: `Searched modules: ${joinOrNone(searchedModules)}. Matched modules: ${joinOrNone(matchedModules)}.`,
      meta: formatCount(searchedModules.length, "searched module"),
      title: target.label,
    };
  }

  if (targetId === "evidence.notSearched") {
    return {
      body: `Not searched: ${joinOrNone(unsearchedModules)}.`,
      meta: formatCount(unsearchedModules.length, "unsearched module"),
      title: target.label,
    };
  }

  if (targetId === "actions.pdpa") {
    return {
      body: `PDPA vendor diligence checklist has ${formatCount(buildPdpaChecklist(dossier).length, "review item")}.`,
      meta: "Action checklist",
      title: target.label,
    };
  }

  if (targetId === "actions.nextChecks") {
    return {
      body: dossier.nextChecks === undefined || dossier.nextChecks.length === 0
        ? "No next checks were returned."
        : dossier.nextChecks.slice(0, 2).map((check) => `${check.tool}: ${check.reason}`).join(" "),
      meta: formatCount(dossier.nextChecks?.length ?? 0, "next check"),
      title: target.label,
    };
  }

  if (targetId === "audit.gaps") {
    return {
      body: dossier.gaps.length === 0
        ? "No lookup gaps were returned."
        : dossier.gaps.slice(0, 2).map((gap) => `${gap.code}: ${gap.message}`).join(" "),
      meta: formatCount(dossier.gaps.length, "gap"),
      title: target.label,
    };
  }

  if (targetId === "audit.provenance") {
    return {
      body: dossier.provenance.length === 0
        ? "No provenance entries were returned."
        : dossier.provenance.slice(0, 3).map((item) => `${item.source}: ${item.coverage}`).join(" "),
      meta: `${formatCount(dossier.provenance.length, "source")} / ${formatCount(dossier.freshness.length, "freshness note")}`,
      title: target.label,
    };
  }

  if (targetId === "audit.handoff") {
    return {
      body: dossier.records.handoff === undefined
        ? "No handoff artifact was returned."
        : "Structured handoff content is available for another analyst or agent.",
      meta: "Audit handoff",
      title: target.label,
    };
  }

  if (targetId === "evidence.webPresence") {
    return {
      body: "Web discovery results are shown separately from official registry evidence.",
      meta: "Supplemental web discovery",
      title: target.label,
    };
  }

  if (targetId === "evidence.peopleDiscovery") {
    return {
      body: "Candidate people references are supplemental and require analyst verification before use.",
      meta: "Supplemental people follow-up",
      title: target.label,
    };
  }

  if (targetId === "overview.memo") {
    return {
      body: "The analyst memo summarizes evidence-backed findings, risk rating, next steps, and confidence blockers.",
      meta: "AI memo",
      title: target.label,
    };
  }

  return {
    body: "Open the referenced section for supporting details.",
    meta: target.tab,
    title: target.label,
  };
}

function resolveSummaryTargetId(dossier: BusinessDossier, targetId: SummaryTargetId): SummaryTargetId {
  return targetId === "audit.gaps" && dossier.gaps.length === 0 ? "audit.provenance" : targetId;
}

function getSummaryPrompt(state: InteractiveSummaryState): InteractiveSummaryPrompt | undefined {
  if (state.status === "ready" || state.status === "unavailable") {
    return state.summary.prompt;
  }
  if (state.status === "error") {
    return state.summary?.prompt;
  }
  if (state.status === "fallback") {
    return state.prompt;
  }
  return undefined;
}

async function copyTextToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    // Fall back for local browser contexts where the async Clipboard API is blocked.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.height = "1px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.width = "1px";
  document.body.appendChild(textarea);
  textarea.focus({ preventScroll: true });
  textarea.select();
  textarea.setSelectionRange(0, text.length);
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("Copy command failed.");
  }
}

function LinkedSummarySection({
  dossier,
  onNavigateTarget,
  state,
}: {
  dossier: BusinessDossier;
  onNavigateTarget: (targetId: SummaryTargetId) => void;
  state: InteractiveSummaryState;
}) {
  const [activePreviewKey, setActivePreviewKey] = useState<string | null>(null);
  const [promptCopyState, setPromptCopyState] = useState<"idle" | "copied" | "error">("idle");
  const promptCopyTimer = useRef<number | null>(null);
  const renderedSegments = state.status === "ready"
    ? state.summary.segments
    : state.status === "fallback"
      ? state.segments
      : [];
  const summaryPrompt = getSummaryPrompt(state);

  useEffect(() => () => {
    if (promptCopyTimer.current !== null) {
      window.clearTimeout(promptCopyTimer.current);
    }
  }, []);

  const copySummaryPrompt = useCallback(async () => {
    if (summaryPrompt === undefined) {
      return;
    }
    try {
      await copyTextToClipboard(summaryPrompt.copyText);
      setPromptCopyState("copied");
      if (promptCopyTimer.current !== null) {
        window.clearTimeout(promptCopyTimer.current);
      }
      promptCopyTimer.current = window.setTimeout(() => setPromptCopyState("idle"), 2000);
    } catch {
      setPromptCopyState("error");
    }
  }, [summaryPrompt]);

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-6">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-normal text-foreground">Summary</h2>
        </div>
        <div className="flex w-fit shrink-0 flex-wrap gap-2">
          {state.status === "ready" ? (
            <span className="w-fit rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
              {state.summary.provider} / {state.summary.model}
            </span>
          ) : state.status === "fallback" ? (
            <span className="w-fit rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
              Local fallback
            </span>
          ) : null}
          {summaryPrompt === undefined ? null : (
            <>
              <textarea
                aria-label="AI synthesis prompt"
                className="sr-only"
                readOnly
                value={summaryPrompt.copyText}
              />
              <button
                aria-label="Copy AI synthesis prompt"
                className={cn(
                  "inline-flex h-7 w-fit items-center gap-1 rounded-md border border-border bg-background px-2 text-xs font-medium text-muted-foreground transition-colors",
                  "hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70",
                  promptCopyState === "error" ? "border-destructive/40 text-destructive" : "",
                )}
                onClick={() => void copySummaryPrompt()}
                title="Copy AI synthesis prompt"
                type="button"
              >
                {promptCopyState === "copied" ? (
                  <Check aria-hidden="true" className="h-3.5 w-3.5" />
                ) : (
                  <Copy aria-hidden="true" className="h-3.5 w-3.5" />
                )}
                {promptCopyState === "copied" ? "Copied" : promptCopyState === "error" ? "Copy failed" : "Copy prompt"}
              </button>
            </>
          )}
        </div>
      </div>

      {state.status === "loading" ? (
        <div className="mt-5 flex min-w-0 items-center gap-3 rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          <Loader2 aria-hidden="true" className="h-4 w-4 shrink-0 animate-spin" />
          <p>Dude is asking the configured server-side AI provider for a linked one-sentence summary.</p>
        </div>
      ) : state.status === "unavailable" ? (
        <div className="mt-5 rounded-md border border-border bg-muted/40 p-4">
          <h3 className="text-sm font-semibold text-foreground">Summary unavailable</h3>
          <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{state.summary.reason.message}</p>
        </div>
      ) : state.status === "error" ? (
        <div className="mt-5 rounded-md border border-destructive/30 bg-destructive/5 p-4">
          <h3 className="text-sm font-semibold text-destructive">Summary failed</h3>
          <p className="mt-2 break-words text-sm leading-6 text-destructive/90">
            {state.summary?.reason.message ?? state.message}
          </p>
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          <p className="break-words text-2xl font-medium leading-10 text-foreground">
            {renderedSegments.map((segment, index) => {
              const targetId = resolveSummaryTargetId(dossier, segment.targetId);
              const target = summaryTargetConfig[targetId];
              const preview = buildSummaryTargetPreview(dossier, targetId);
              const previewKey = `${segment.targetId}-${index}`;
              if (!segment.emphasized) {
                return <span key={previewKey}>{segment.text}</span>;
              }

              return (
                <span
                  className="group/summary-link relative inline-block"
                  key={previewKey}
                  onBlur={() => setActivePreviewKey(null)}
                  onFocus={() => setActivePreviewKey(previewKey)}
                  onMouseEnter={() => setActivePreviewKey(previewKey)}
                  onMouseLeave={() => setActivePreviewKey(null)}
                  onMouseMove={() => setActivePreviewKey(previewKey)}
                  onPointerEnter={() => setActivePreviewKey(previewKey)}
                  onPointerLeave={() => setActivePreviewKey(null)}
                  onPointerMove={() => setActivePreviewKey(previewKey)}
                >
                  <button
                    aria-describedby={`summary-preview-${index}`}
                    aria-label={`Open ${target.label}`}
                    className={cn(
                      "inline rounded-sm font-semibold text-foreground underline decoration-border decoration-2 underline-offset-4 outline-offset-4 transition-colors",
                      "hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70",
                    )}
                    onClick={() => onNavigateTarget(targetId)}
                    type="button"
                  >
                    <strong>{segment.text}</strong>
                  </button>
                  <span
                    className={cn(
                      "pointer-events-none absolute bottom-full left-1/2 z-20 mb-3 w-[min(22rem,calc(100vw-3rem))] -translate-x-1/2 rounded-lg border border-border bg-popover p-3 text-left text-sm leading-6 text-popover-foreground shadow-lg",
                      activePreviewKey === previewKey ? "block" : "hidden group-hover/summary-link:block group-focus-within/summary-link:block",
                    )}
                    id={`summary-preview-${index}`}
                    role="tooltip"
                  >
                    <span className="block text-xs font-medium uppercase text-muted-foreground">{preview.meta}</span>
                    <span className="mt-1 block text-sm font-semibold text-foreground">{preview.title}</span>
                    <span className="mt-1 block text-sm font-normal text-muted-foreground">{preview.body}</span>
                    <span className="mt-2 block text-xs font-medium text-foreground">Click to open this section.</span>
                  </span>
                </span>
              );
            })}
          </p>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="rounded-full bg-muted px-2.5 py-1">
              {state.status === "ready"
                ? `Generated ${formatTimestamp(state.summary.generatedAt) ?? state.summary.generatedAt}`
                : `Generated ${formatTimestamp(state.generatedAt) ?? state.generatedAt}`}
            </span>
            <span className="rounded-full bg-muted px-2.5 py-1">
              {renderedSegments.filter((segment) => segment.emphasized).length} linked sections
            </span>
            {state.status === "fallback" ? (
              <span className="rounded-full bg-muted px-2.5 py-1" title={state.reason}>
                AI summary unavailable
              </span>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}

const tabTriggerClassName =
  "group min-w-0 flex-1 flex-col gap-1 border border-transparent px-2 py-3 text-xs data-[state=active]:border-border data-[state=active]:bg-card data-[state=active]:shadow-sm";

export function DossierFindingsTabs({
  dossier,
  isPdpaExporting,
  memoState,
  onExportPdpaReport,
  onModuleFollowUp,
  peopleDiscoveryState,
  rerunningModule,
  sharedMemoState,
  webPresenceState,
}: DossierFindingsTabsProps) {
  const [activeTab, setActiveTab] = useState<FindingsTabValue>("summary");
  const [summaryState, setSummaryState] = useState<InteractiveSummaryState>({ status: "loading" });
  const pdpaItemCount = useMemo(() => buildPdpaChecklist(dossier).length, [dossier]);
  const searchedModuleCount = dossier.records.resolution?.searchedModules?.length ?? 0;
  const matchedModuleCount = dossier.records.resolution?.matchedModules?.length ?? 0;
  const nextCheckCount = dossier.nextChecks?.length ?? 0;
  const missingCount = dossier.gaps.length;
  const hasMissingEvidence = missingCount > 0;
  const auditCount = dossier.provenance.length + dossier.freshness.length;
  const summaryLinkCount = summaryState.status === "ready"
    ? Math.max(1, summaryState.summary.segments.filter((segment) => segment.emphasized).length)
    : summaryState.status === "fallback"
      ? Math.max(1, summaryState.segments.filter((segment) => segment.emphasized).length)
    : 1;
  const tabs: FindingsTab[] = [
    {
      count: summaryLinkCount,
      icon: Sparkles,
      label: "Summary",
      value: "summary",
    },
    {
      count: 5,
      icon: LayoutDashboard,
      label: "Overview",
      value: "overview",
    },
    {
      count: Math.max(1, Math.max(matchedModuleCount, searchedModuleCount)),
      icon: Database,
      label: "Evidence",
      value: "evidence",
    },
    {
      count: pdpaItemCount + nextCheckCount,
      icon: ClipboardCheck,
      label: "Actions",
      value: "actions",
    },
    {
      count: auditCount,
      icon: FileSearch,
      label: "Audit",
      value: "audit",
    },
    ...(hasMissingEvidence
      ? [{
          count: missingCount,
          icon: FileQuestion,
          label: "Missing",
          value: "missing" as const,
        }]
      : []),
  ];

  useEffect(() => {
    const controller = new AbortController();
    setSummaryState({ status: "loading" });
    const fallback = (reason: string, prompt?: InteractiveSummaryPrompt): InteractiveSummaryState => ({
      generatedAt: new Date().toISOString(),
      ...(prompt === undefined ? {} : { prompt }),
      reason,
      segments: buildFallbackInteractiveSummary(dossier),
      status: "fallback",
    });
    void postGatewayJson<InteractiveSummaryResponse>(
      "/api/v1/dude/summary",
      { dossier },
      { signal: controller.signal },
    )
      .then((summary) => {
        if (controller.signal.aborted) {
          return;
        }
        if (summary.status === "ready") {
          setSummaryState({ status: "ready", summary });
        } else if (summary.status === "unavailable") {
          setSummaryState(fallback(summary.reason.message, summary.prompt));
        } else {
          setSummaryState(fallback(summary.reason.message, summary.prompt));
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setSummaryState(fallback(error instanceof Error ? error.message : "Summary request failed."));
        }
      });

    return () => controller.abort();
  }, [dossier]);

  const navigateToSummaryTarget = useCallback((targetId: SummaryTargetId) => {
    const target = summaryTargetConfig[targetId];
    if (target.tab === "missing" && !hasMissingEvidence) {
      return;
    }
    setActiveTab(target.tab);
    window.setTimeout(() => {
      const element = document.getElementById(target.elementId);
      if (element === null) {
        return;
      }
      element.scrollIntoView({ behavior: "smooth", block: "start" });
      element.focus({ preventScroll: true });
    }, 80);
  }, [hasMissingEvidence]);

  return (
    <Tabs className="min-w-0" onValueChange={(value) => setActiveTab(value as FindingsTabValue)} value={activeTab}>
      <TabsList className={cn(
        "grid w-full grid-cols-2 gap-1 bg-muted/60 p-1 md:grid-cols-3",
        hasMissingEvidence ? "lg:grid-cols-6" : "lg:grid-cols-5",
      )}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <TabsTrigger className={tabTriggerClassName} key={tab.value} value={tab.value}>
              <span className="flex min-w-0 items-center gap-2">
                <Icon aria-hidden="true" className="h-4 w-4 shrink-0 transition-opacity group-data-[state=inactive]:opacity-50" />
                <span className="truncate">{tab.label}</span>
              </span>
              <span className="min-w-5 rounded-full bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground transition-opacity group-data-[state=inactive]:opacity-50">
                {tabCountLabel(tab.count)}
              </span>
            </TabsTrigger>
          );
        })}
      </TabsList>

      <TabsContent className="mt-5 space-y-5" value="summary">
        <LinkedSummarySection
          dossier={dossier}
          onNavigateTarget={navigateToSummaryTarget}
          state={summaryState}
        />
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="overview">
        <SectionAnchor id="dossier-overview-summary">
          <SummarySection dossier={dossier} />
        </SectionAnchor>
        <SectionAnchor id="dossier-overview-snapshot">
          <SnapshotSection dossier={dossier} />
        </SectionAnchor>
        <SectionAnchor id="dossier-overview-risk">
          <RiskSection dossier={dossier} />
        </SectionAnchor>
        <SectionAnchor id="dossier-overview-memo">
          <AnalystMemoSection sharedState={sharedMemoState} state={memoState} />
        </SectionAnchor>
        <SectionAnchor id="dossier-overview-confidence">
          <ConfidenceSection dossier={dossier} />
        </SectionAnchor>
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="evidence">
        <EvidenceSection dossier={dossier} onModuleFollowUp={onModuleFollowUp} runningModule={rerunningModule} />
        <SectionAnchor id="dossier-evidence-web">
          <WebPresenceSection state={webPresenceState} />
        </SectionAnchor>
        <SectionAnchor id="dossier-evidence-people">
          <PeopleDiscoverySection state={peopleDiscoveryState} />
        </SectionAnchor>
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="actions">
        <SectionAnchor id="dossier-actions-pdpa">
          <PdpaChecklistSection
            dossier={dossier}
            isExporting={isPdpaExporting}
            onExportReport={onExportPdpaReport}
          />
        </SectionAnchor>
        <SectionAnchor id="dossier-actions-next-checks">
          <NextChecksSection dossier={dossier} />
        </SectionAnchor>
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="audit">
        <SectionAnchor id="dossier-audit-handoff">
          <HandoffSection dossier={dossier} />
        </SectionAnchor>
        <SectionAnchor id="dossier-audit-provenance">
          <ProvenanceSection dossier={dossier} />
        </SectionAnchor>
      </TabsContent>

      {hasMissingEvidence ? (
        <TabsContent className="mt-5 space-y-5" value="missing">
          <SectionAnchor id="dossier-missing-gaps">
            <GapsSection dossier={dossier} />
          </SectionAnchor>
        </TabsContent>
      ) : null}
    </Tabs>
  );
}
