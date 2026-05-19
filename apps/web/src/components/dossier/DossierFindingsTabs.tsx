import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  FileDown,
  FileText,
  ListChecks,
  SearchCheck,
  ShieldAlert,
} from "lucide-react";
import { useMemo, useState } from "react";

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
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DEFAULT_REPORT_TEMPLATE,
  REPORT_SECTION_DESCRIPTIONS,
  REPORT_SECTION_LABELS,
  REPORT_WRITING_STYLE_DESCRIPTIONS,
  REPORT_WRITING_STYLE_LABELS,
  moveReportSection,
  toggleReportSection,
  type ReportExportFormat,
  type ReportSectionId,
  type ReportTemplate,
  type ReportWritingStyle,
} from "@/lib/report-template";
import { cn } from "@/lib/utils";
import type { AnalystMemoCitation } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

type DossierFindingsTabsProps = {
  dossier: BusinessDossier;
  isPdpaExporting: boolean;
  memoState: AnalystMemoState;
  onExportPdpaReport: (reviewedItemIds: readonly string[]) => void;
  onExportReport?: (template: ReportTemplate, format: ReportExportFormat) => void;
  onModuleFollowUp: (request: ModuleFollowUpRequest) => void;
  peopleDiscoveryState: PeopleDiscoveryState;
  rerunningModule: RunningBusinessModule;
  sharedMemoState: string | null;
  webPresenceState: WebPresenceState;
};

type EvidenceDialogState =
  | { kind: "citation"; citation: AnalystMemoCitation }
  | { kind: "pack"; title: string; description: string }
  | null;

const writingStyles: ReportWritingStyle[] = [
  "concise_analyst",
  "audit_ready_formal",
  "client_friendly_neutral",
  "internal_escalation",
];

function SummaryFallback({ dossier }: { dossier: BusinessDossier }) {
  return (
    <div className="space-y-3">
      {dossier.summary.slice(0, 6).map((item) => (
        <button
          className="block w-full rounded-md border border-border bg-background p-3 text-left transition hover:bg-muted/50"
          key={`${item.label}-${item.source ?? ""}`}
          type="button"
        >
          <span className="block text-xs font-medium uppercase text-muted-foreground">{item.label}</span>
          <span className="mt-1 block break-words text-sm text-foreground">
            {item.value === null || item.value === undefined || item.value === "" ? "-" : String(item.value)}
          </span>
          {item.source === undefined || item.source === null ? null : (
            <span className="mt-1 block text-xs text-muted-foreground">Source: {item.source}</span>
          )}
        </button>
      ))}
    </div>
  );
}

function CitedSummary({
  dossier,
  memoState,
  onOpenEvidence,
}: {
  dossier: BusinessDossier;
  memoState: AnalystMemoState;
  onOpenEvidence: (state: EvidenceDialogState) => void;
}) {
  if (memoState.status !== "ready") {
    return (
      <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <FileText className="mt-0.5 h-5 w-5 text-muted-foreground" />
          <div>
            <h2 className="text-xl font-semibold text-foreground">CDD Summary</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              AI summary is {memoState.status}. The registry summary below remains available for analyst review.
            </p>
          </div>
        </div>
        <div className="mt-5">
          <SummaryFallback dossier={dossier} />
        </div>
      </section>
    );
  }

  const memo = memoState.memo;
  const citationById = new Map(memo.citations.map((citation) => [citation.id, citation]));

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex min-w-0 flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">CDD report draft</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-normal text-foreground">Cited executive summary</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Every finding links back to a source reference. Use this as an analyst-review report draft, not a pass/fail opinion.
          </p>
        </div>
        <span className="w-fit rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
          {memo.provider} / {memo.model}
        </span>
      </div>

      <div className="mt-5 grid gap-4">
        {memo.evidenceMemo.length === 0 ? (
          <p className="rounded-md border border-border bg-muted/35 p-4 text-sm text-muted-foreground">
            No cited memo findings were returned.
          </p>
        ) : (
          memo.evidenceMemo.map((item, index) => (
            <article className="rounded-md border border-border bg-background p-4" key={`${item.text}-${index}`}>
              <p className="text-sm font-semibold text-muted-foreground">Finding {index + 1}</p>
              <p className="mt-2 break-words text-base leading-7 text-foreground">{item.text}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {item.citationIds.map((id) => {
                  const citation = citationById.get(id);
                  return (
                    <Button
                      className="h-8 rounded-full font-mono text-xs"
                      disabled={citation === undefined}
                      key={id}
                      onClick={() => {
                        if (citation !== undefined) {
                          onOpenEvidence({ citation, kind: "citation" });
                        }
                      }}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {id}
                    </Button>
                  );
                })}
              </div>
            </article>
          ))
        )}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1fr)]">
        <article className="rounded-md border border-border bg-background p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">Risk rating: {memo.riskRating.level}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{memo.riskRating.rationale}</p>
            </div>
          </div>
        </article>
        <article className="rounded-md border border-border bg-background p-4">
          <div className="flex items-start gap-3">
            <ListChecks className="mt-0.5 h-5 w-5 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">Required follow-up</h3>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {memo.decisionAid.nextSteps.map((step) => <li key={step}>{step}</li>)}
              </ul>
            </div>
          </div>
        </article>
      </div>

      {memo.decisionAid.confidenceBlockers.length === 0 ? null : (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-amber-950">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5" />
            <div>
              <h3 className="text-sm font-semibold">Confidence blockers</h3>
              <ul className="mt-2 space-y-2 text-sm leading-6">
                {memo.decisionAid.confidenceBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function ReportBuilder({
  onExportReport,
}: {
  onExportReport: (template: ReportTemplate, format: ReportExportFormat) => void;
}) {
  const [template, setTemplate] = useState<ReportTemplate>(DEFAULT_REPORT_TEMPLATE);

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex min-w-0 flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Report Builder</p>
          <h2 className="mt-1 text-xl font-semibold text-foreground">Choose report pages and writing style</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Build the review artifact from the same cited dossier evidence. The executive summary is always included.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onExportReport(template, "pdf")} type="button">
            <FileDown className="mr-2 h-4 w-4" />
            Export PDF
          </Button>
          <Button onClick={() => onExportReport(template, "docx")} type="button" variant="outline">
            <FileText className="mr-2 h-4 w-4" />
            Export DOCX
          </Button>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <label className="block rounded-md border border-border bg-background p-4">
          <span className="text-sm font-semibold text-foreground">Writing preset</span>
          <select
            aria-label="Report writing style"
            className="mt-3 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            onChange={(event) => setTemplate((current) => ({
              ...current,
              writingStyle: event.target.value as ReportWritingStyle,
            }))}
            value={template.writingStyle}
          >
            {writingStyles.map((style) => (
              <option key={style} value={style}>{REPORT_WRITING_STYLE_LABELS[style]}</option>
            ))}
          </select>
          <span className="mt-2 block text-sm leading-6 text-muted-foreground">
            {REPORT_WRITING_STYLE_DESCRIPTIONS[template.writingStyle]}
          </span>
        </label>

        <div className="rounded-md border border-border bg-background p-4">
          <h3 className="text-sm font-semibold text-foreground">Sections</h3>
          <div className="mt-3 grid gap-2">
            {DEFAULT_REPORT_TEMPLATE.sections.map((section) => {
              const selected = template.sections.includes(section);
              const index = template.sections.indexOf(section);
              return (
                <div
                  className={cn(
                    "grid gap-3 rounded-md border p-3 sm:grid-cols-[minmax(0,1fr)_auto]",
                    selected ? "border-border bg-card" : "border-border/70 bg-muted/40 text-muted-foreground",
                  )}
                  key={section}
                >
                  <label className="flex min-w-0 items-start gap-3">
                    <input
                      checked={selected}
                      className="mt-1"
                      disabled={section === "executive_summary"}
                      onChange={() => setTemplate((current) => ({
                        ...current,
                        sections: toggleReportSection(current.sections, section),
                      }))}
                      type="checkbox"
                    />
                    <span>
                      <span className="block text-sm font-semibold">{REPORT_SECTION_LABELS[section]}</span>
                      <span className="mt-1 block text-xs leading-5">{REPORT_SECTION_DESCRIPTIONS[section]}</span>
                    </span>
                  </label>
                  <div className="flex gap-1">
                    <Button
                      aria-label={`Move ${REPORT_SECTION_LABELS[section]} up`}
                      className="h-8 w-8"
                      disabled={!selected || index <= 0}
                      onClick={() => setTemplate((current) => ({
                        ...current,
                        sections: moveReportSection(current.sections, section, "up"),
                      }))}
                      size="icon"
                      type="button"
                      variant="ghost"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      aria-label={`Move ${REPORT_SECTION_LABELS[section]} down`}
                      className="h-8 w-8"
                      disabled={!selected || index === -1 || index >= template.sections.length - 1}
                      onClick={() => setTemplate((current) => ({
                        ...current,
                        sections: moveReportSection(current.sections, section, "down"),
                      }))}
                      size="icon"
                      type="button"
                      variant="ghost"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function EvidenceDialog({
  state,
  onOpenChange,
}: {
  onOpenChange: (open: boolean) => void;
  state: EvidenceDialogState;
}) {
  return (
    <Dialog open={state !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-3xl overflow-y-auto">
        {state === null ? null : state.kind === "citation" ? (
          <>
            <DialogHeader>
              <DialogTitle>{state.citation.id}</DialogTitle>
              <DialogDescription>{state.citation.source}</DialogDescription>
            </DialogHeader>
            <article className="rounded-md border border-border bg-muted/30 p-4">
              <p className="text-sm font-semibold text-foreground">{state.citation.label}</p>
              <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                {state.citation.text}
              </p>
            </article>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{state.title}</DialogTitle>
              <DialogDescription>{state.description}</DialogDescription>
            </DialogHeader>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function DossierFindingsTabs({
  dossier,
  isPdpaExporting,
  memoState,
  onExportPdpaReport,
  onExportReport = () => undefined,
  onModuleFollowUp,
  peopleDiscoveryState,
  rerunningModule,
  sharedMemoState,
  webPresenceState,
}: DossierFindingsTabsProps) {
  const [evidenceDialog, setEvidenceDialog] = useState<EvidenceDialogState>(null);
  const evidenceStats = useMemo(() => ({
    gaps: dossier.gaps.length,
    provenance: dossier.provenance.length,
    records: Object.values(dossier.records)
      .reduce((sum, value) => sum + (Array.isArray(value) ? value.length : 0), 0),
  }), [dossier]);

  return (
    <div className="space-y-5">
      <CitedSummary dossier={dossier} memoState={memoState} onOpenEvidence={setEvidenceDialog} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.55fr)]">
        <ReportBuilder onExportReport={onExportReport} />
        <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <p className="text-sm font-medium text-muted-foreground">Evidence pack</p>
          <h2 className="mt-1 text-xl font-semibold text-foreground">Available on demand</h2>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-sm">
            <div className="rounded-md border border-border p-3">
              <p className="text-lg font-semibold">{evidenceStats.records}</p>
              <p className="text-xs text-muted-foreground">records</p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-lg font-semibold">{evidenceStats.provenance}</p>
              <p className="text-xs text-muted-foreground">sources</p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-lg font-semibold">{evidenceStats.gaps}</p>
              <p className="text-xs text-muted-foreground">gaps</p>
            </div>
          </div>
          <Button
            className="mt-4 w-full"
            onClick={() => setEvidenceDialog({
              description: "Scroll the evidence pack below for raw rows, source attribution, gaps, and follow-up actions.",
              kind: "pack",
              title: "Evidence pack",
            })}
            type="button"
            variant="outline"
          >
            <SearchCheck className="mr-2 h-4 w-4" />
            How evidence works
          </Button>
        </section>
      </div>

      <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 h-5 w-5 text-muted-foreground" />
          <div>
            <h2 className="text-xl font-semibold text-foreground">Evidence Pack</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              These details support the summary and report exports. Supplemental discovery is not official registry evidence.
            </p>
          </div>
        </div>
        <div className="mt-5 space-y-5">
          <SnapshotSection dossier={dossier} />
          <RiskSection dossier={dossier} />
          <ConfidenceSection dossier={dossier} />
          <EvidenceSection dossier={dossier} onModuleFollowUp={onModuleFollowUp} runningModule={rerunningModule} />
          <WebPresenceSection state={webPresenceState} />
          <PeopleDiscoverySection state={peopleDiscoveryState} />
          <PdpaChecklistSection
            dossier={dossier}
            isExporting={isPdpaExporting}
            onExportReport={onExportPdpaReport}
          />
          <NextChecksSection dossier={dossier} />
          <GapsSection dossier={dossier} />
          <ProvenanceSection dossier={dossier} />
          <HandoffSection dossier={dossier} />
          <AnalystMemoSection sharedState={sharedMemoState} state={memoState} />
        </div>
      </section>

      <EvidenceDialog
        onOpenChange={(open) => {
          if (!open) setEvidenceDialog(null);
        }}
        state={evidenceDialog}
      />
    </div>
  );
}
