import type { ReactNode } from "react";

import {
  buildDiligenceSnapshot,
  confidenceLabel,
  formatRecordValue,
  getActionableSourceCoverageGaps,
  getDossierRecordGroups,
  getSourceCoverage,
  riskCodeLabel,
  riskSeverityLabel,
  sourceCoverageLevelLabel,
  sourceCoverageStatusLabel,
} from "@/lib/dossier";
import {
  REPORT_SECTION_LABELS,
  REPORT_WRITING_STYLE_LABELS,
  type ReportSectionId,
  type ReportTemplate,
} from "@/lib/report-template";
import { buildSourceUseWarnings } from "@/lib/source-use-warnings";
import type { BusinessDossier, BriefSummaryItem } from "@/types/dossier";
import type { AnalystMemoState } from "@/components/dossier/AnalystMemoSection";
import type { PeopleDiscoveryState } from "@/components/dossier/PeopleDiscoverySection";
import type { WebPresenceState } from "@/components/dossier/WebPresenceSection";

type ReportPreviewProps = {
  dossier: BusinessDossier;
  memoState: AnalystMemoState;
  peopleDiscoveryState: PeopleDiscoveryState;
  template: ReportTemplate;
  webPresenceState: WebPresenceState;
};

type PreviewLine = {
  label?: string;
  value: string;
};

const stringifyPreviewValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
};

const summaryLines = (rows: readonly BriefSummaryItem[], limit = 6): PreviewLine[] =>
  rows.slice(0, limit).map((row) => ({
    label: row.label,
    value: `${stringifyPreviewValue(row.value)}${row.source === undefined || row.source === null ? "" : ` (${row.source})`}`,
  }));

function PreviewSection({
  children,
  id,
}: {
  children: ReactNode;
  id: ReportSectionId | "source_warnings";
}) {
  const title = id === "source_warnings" ? "Source-use warnings" : REPORT_SECTION_LABELS[id];
  return (
    <section className="border-t border-slate-200 pt-3">
      <h4 className="text-[11px] font-bold uppercase tracking-wide text-slate-950">{title}</h4>
      <div className="mt-2 space-y-1.5 text-[11px] leading-5 text-slate-700">{children}</div>
    </section>
  );
}

function PreviewRows({ rows }: { rows: readonly PreviewLine[] }) {
  if (rows.length === 0) {
    return <p className="text-slate-500">No rows will be printed for this section.</p>;
  }
  return (
    <dl className="space-y-1.5">
      {rows.map((row, index) => (
        <div className="min-w-0" key={`${row.label ?? "row"}-${row.value}-${index}`}>
          {row.label === undefined ? null : (
            <dt className="inline font-semibold text-slate-950">{row.label}: </dt>
          )}
          <dd className="inline break-words">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function executiveSummaryRows(dossier: BusinessDossier, memoState: AnalystMemoState): PreviewLine[] {
  if (memoState.status === "ready") {
    const memo = memoState.memo;
    return [
      { label: "Risk rating", value: `${memo.riskRating.level}: ${memo.riskRating.rationale}` },
      ...memo.evidenceMemo.slice(0, 3).map((finding, index) => ({
        label: `Finding ${index + 1}`,
        value: `${finding.text} [${finding.citationIds.join(", ")}]`,
      })),
    ];
  }
  return summaryLines(dossier.summary);
}

function riskRows(dossier: BusinessDossier, memoState: AnalystMemoState): PreviewLine[] {
  const rows: PreviewLine[] = [];
  if (memoState.status === "ready") {
    rows.push({
      label: "Memo risk",
      value: `${memoState.memo.riskRating.level}: ${memoState.memo.riskRating.rationale}`,
    });
  }
  rows.push(...(dossier.riskFlags ?? []).slice(0, 4).map((flag) => ({
    label: `${riskSeverityLabel(flag)} - ${riskCodeLabel(flag.code)}`,
    value: `${flag.message} (${flag.source})`,
  })));
  rows.push(...(dossier.matchConfidence ?? []).slice(0, 3).map((match) => ({
    label: match.source,
    value: `${confidenceLabel(match.confidence)}${match.matchedOn === null ? "" : ` on ${match.matchedOn}`}`,
  })));
  return rows;
}

function actionRows(dossier: BusinessDossier, memoState: AnalystMemoState): PreviewLine[] {
  const rows: PreviewLine[] = [];
  if (memoState.status === "ready") {
    rows.push(...memoState.memo.decisionAid.nextSteps.slice(0, 5).map((step, index) => ({
      label: `Next action ${index + 1}`,
      value: step,
    })));
    rows.push(...memoState.memo.decisionAid.confidenceBlockers.slice(0, 3).map((blocker, index) => ({
      label: `Blocker ${index + 1}`,
      value: blocker,
    })));
  }
  rows.push(...(dossier.nextChecks ?? []).slice(0, 4).map((check) => ({
    label: check.tool,
    value: check.reason,
  })));
  return rows;
}

function identityRows(dossier: BusinessDossier): PreviewLine[] {
  const snapshot = buildDiligenceSnapshot(dossier);
  return [
    { label: "Entity", value: snapshot.entityName ?? "Not available" },
    { label: "UEN", value: snapshot.uen ?? "Not available" },
    { label: "Status", value: snapshot.status ?? "Not available" },
    { label: "Entity type", value: snapshot.entityType ?? "Not available" },
    { label: "Address", value: snapshot.address ?? "Not available" },
    { label: "Primary SSIC", value: snapshot.primarySsic ?? "Not available" },
    { label: "Matched modules", value: snapshot.matchedModules },
    { label: "Confidence", value: snapshot.confidence ?? "Not available" },
  ];
}

function evidenceRows(dossier: BusinessDossier): PreviewLine[] {
  const groupRows = getDossierRecordGroups(dossier).flatMap((group) =>
    group.tables.map((table) => ({
      label: `${group.label} / ${table.label}`,
      value: `${table.records.length} record${table.records.length === 1 ? "" : "s"}`,
    })),
  );
  return [...summaryLines(dossier.evidence, 5), ...groupRows].slice(0, 10);
}

function coverageRows(dossier: BusinessDossier): PreviewLine[] {
  return getSourceCoverage(dossier).map((item) => ({
    label: item.label,
    value: `${sourceCoverageStatusLabel(item.status)}; ${sourceCoverageLevelLabel(item.coverageLevel)}; ${item.recordCount} record(s). ${item.reason}`,
  }));
}

function gapRows(dossier: BusinessDossier): PreviewLine[] {
  if (dossier.gaps.length > 0) {
    return dossier.gaps.slice(0, 6).map((gap) => ({ label: gap.code, value: gap.message }));
  }
  const coverageGaps = getActionableSourceCoverageGaps(dossier);
  if (coverageGaps.length > 0) {
    return coverageGaps.slice(0, 6).map((item) => ({
      label: item.label,
      value: item.reason,
    }));
  }
  return [{ label: "Gaps", value: "No gaps returned." }];
}

function supplementalRows(
  peopleDiscoveryState: PeopleDiscoveryState,
  webPresenceState: WebPresenceState,
): PreviewLine[] {
  const rows: PreviewLine[] = [];
  if (webPresenceState.status === "success") {
    rows.push(
      { label: "Web discovery", value: `${webPresenceState.presence.results.length} result(s)` },
      { label: "Possible official website", value: webPresenceState.presence.possibleOfficialWebsite ?? "Not returned" },
    );
    rows.push(...webPresenceState.presence.results.slice(0, 3).map((result) => ({
      label: result.siteName ?? result.url,
      value: result.title,
    })));
  } else {
    rows.push({ label: "Web discovery", value: webPresenceState.status });
  }
  if (peopleDiscoveryState.status === "success") {
    rows.push({ label: "People discovery", value: `${peopleDiscoveryState.discovery.results.length} candidate snippet(s)` });
  } else {
    rows.push({ label: "People discovery", value: peopleDiscoveryState.status });
  }
  return rows;
}

function manifestRows(template: ReportTemplate): PreviewLine[] {
  return [
    { label: "Report style", value: REPORT_WRITING_STYLE_LABELS[template.writingStyle] },
    { label: "Sections", value: template.sections.map((section) => REPORT_SECTION_LABELS[section]).join(", ") },
    { label: "Manifest", value: "Hash, schema version, signature, and source-use warnings are generated at export time." },
  ];
}

function sectionRows({
  dossier,
  memoState,
  peopleDiscoveryState,
  section,
  template,
  webPresenceState,
}: ReportPreviewProps & { section: ReportSectionId }): PreviewLine[] {
  switch (section) {
    case "executive_summary":
      return executiveSummaryRows(dossier, memoState);
    case "coverage_matrix":
      return coverageRows(dossier);
    case "risk_assessment":
      return riskRows(dossier, memoState);
    case "action_plan":
      return actionRows(dossier, memoState);
    case "identity_snapshot":
      return identityRows(dossier);
    case "evidence_records":
      return evidenceRows(dossier);
    case "supplemental_discovery":
      return supplementalRows(peopleDiscoveryState, webPresenceState);
    case "gaps":
      return gapRows(dossier);
    case "provenance":
      return dossier.provenance.slice(0, 6).map((item) => ({
        label: item.source,
        value: `${item.tool}; ${item.coverage}; ${item.recordCount} record(s)`,
      }));
    case "freshness":
      return dossier.freshness.slice(0, 6).map((item) => ({
        label: item.source,
        value: `Observed ${formatRecordValue("observedAt", item.observedAt)}; upstream ${formatRecordValue("upstreamTimestamp", item.upstreamTimestamp ?? null)}`,
      }));
    case "limits":
      return dossier.limits.slice(0, 6).map((limit) => ({ label: limit.code, value: limit.message }));
    case "manifest":
      return manifestRows(template);
    default:
      return [];
  }
}

export function ReportPreview({
  dossier,
  memoState,
  peopleDiscoveryState,
  template,
  webPresenceState,
}: ReportPreviewProps) {
  const sourceWarnings = buildSourceUseWarnings({
    dossier,
    ...(webPresenceState.status === "success" ? { webPresence: webPresenceState.presence } : {}),
  });

  return (
    <section className="rounded-md border border-border bg-background p-4">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Generated document preview</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Updates from the selected writing preset, section order, and included evidence.
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {template.sections.length} sections
        </span>
      </div>

      <div className="mt-4 max-h-[34rem] overflow-y-auto rounded-md border border-border bg-slate-50 p-3">
        <article className="mx-auto min-h-[36rem] max-w-[34rem] rounded-sm border border-slate-200 bg-white p-5 shadow-sm">
          <header className="border-b border-slate-200 pb-4">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Dude CDD review report</p>
            <h4 className="mt-1 break-words text-lg font-bold leading-6 text-slate-950">{dossier.title}</h4>
            <p className="mt-2 text-[11px] leading-5 text-slate-600">
              Style: {REPORT_WRITING_STYLE_LABELS[template.writingStyle]}. Generated timestamp and export manifest are added when the file is created.
            </p>
          </header>

          <div className="mt-4 space-y-4">
            {sourceWarnings.length === 0 ? null : (
              <PreviewSection id="source_warnings">
                <PreviewRows
                  rows={sourceWarnings.slice(0, 3).map((warning) => ({
                    label: warning.title,
                    value: `${warning.message} Triggered by: ${warning.triggeredBy.join(", ")}`,
                  }))}
                />
              </PreviewSection>
            )}
            {template.sections.map((section) => (
              <PreviewSection id={section} key={section}>
                <PreviewRows
                  rows={sectionRows({
                    dossier,
                    memoState,
                    peopleDiscoveryState,
                    section,
                    template,
                    webPresenceState,
                  })}
                />
              </PreviewSection>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
