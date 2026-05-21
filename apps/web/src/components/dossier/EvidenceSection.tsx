import { useEffect, useState } from "react";

import { RecordTable } from "@/components/dossier/RecordTable";
import type { AgentPlanTask } from "@/components/ui/agent-plan";
import { AgentPlan } from "@/components/ui/agent-plan-loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ALL_FOLLOW_UP_BUSINESS_MODULES,
  BUSINESS_MODULE_FOLLOW_UPS,
  BUSINESS_MODULE_LABELS,
  formatLabel,
  formatRecordValue,
  getDossierRecordGroups,
  getSourceCoverage,
  getSummaryString,
  sourceCoverageLevelLabel,
  sourceCoverageStatusLabel,
  type FollowUpBusinessModule,
} from "@/lib/dossier";
import type {
  BusinessDossier,
  BusinessDossierModule,
  BusinessDossierModuleReason,
  EvidenceGap,
  SectorWorkflowGuideItem,
} from "@/types/dossier";

export type ModuleFollowUpRequest = {
  kind?: "module";
  module: FollowUpBusinessModule;
  value: string;
} | {
  kind: "all";
  modules: readonly FollowUpBusinessModule[];
  value: string;
};

export type RunningBusinessModule = BusinessDossierModule | "all" | null;

const GAP_MODULE_MATCHERS: readonly [BusinessDossierModule, RegExp][] = [
  ["acra", /^ACRA_/],
  ["bca", /^BCA_/],
  ["cea", /^CEA_/],
  ["gebiz", /^GEBIZ_/],
  ["boa", /^BOA_/],
  ["hsa", /^HSA_/],
  ["hlb", /^HLB_/],
];

function getGapModule(gap: EvidenceGap): BusinessDossierModule | null {
  return GAP_MODULE_MATCHERS.find(([, pattern]) => pattern.test(gap.code))?.[0] ?? null;
}

function isUnavailableGap(gap: EvidenceGap): boolean {
  return /UNAVAILABLE|FAILED|TIMEOUT|RATE_LIMIT/i.test(gap.code);
}

function moduleGaps(module: BusinessDossierModule, gaps: EvidenceGap[]): EvidenceGap[] {
  return gaps.filter((gap) => getGapModule(gap) === module);
}

function coverageStatusClassName(status: string): string {
  if (status === "checked") return "border-emerald-200 bg-emerald-50 text-emerald-900";
  if (status === "credential_blocked") return "border-amber-200 bg-amber-50 text-amber-900";
  if (status === "unavailable") return "border-destructive/30 bg-destructive/5 text-destructive";
  return "border-border bg-muted/50 text-muted-foreground";
}

function moduleStatus(
  reason: BusinessDossierModuleReason,
  gaps: EvidenceGap[],
): { label: string; className: string } {
  if (gaps.some(isUnavailableGap)) {
    return {
      label: "Unavailable",
      className: "border-destructive/30 bg-destructive/5 text-destructive",
    };
  }
  if (reason.status === "matched") {
    return {
      label: "Matched",
      className: "border-border bg-card text-foreground",
    };
  }
  if (reason.status === "unmatched") {
    return {
      label: "No match",
      className: "border-border bg-muted/50 text-foreground",
    };
  }
  if (reason.status === "needs_identifier") {
    return {
      label: "Needs identifier",
      className: "border-amber-200 bg-amber-50 text-amber-900",
    };
  }
  return {
    label: reason.status === "unsearched" ? "Not searched" : "Skipped",
    className: "border-border bg-background text-muted-foreground",
  };
}

const selectionReasonLabels: Record<BusinessDossierModuleReason["selectedBy"][number], string> = {
  analyst_rerun: "Analyst rerun",
  default: "Default identity lookup",
  explicit_module: "Explicit user choice",
  inferred_sector: "ACRA/SSIC inference",
  sector_hint: "Explicit sector hint",
  web_hint: "Web hint",
};

function selectionReasonText(reason: BusinessDossierModuleReason): string {
  return reason.selectedBy.length === 0
    ? "Not selected"
    : reason.selectedBy.map((item) => selectionReasonLabels[item]).join(", ");
}

function guideForModule(
  guides: readonly SectorWorkflowGuideItem[],
  module: BusinessDossierModule,
): SectorWorkflowGuideItem | undefined {
  return guides.find((guide) => guide.retainedModules.includes(module));
}

function SectorWorkflowGuide({ guides }: { guides: readonly SectorWorkflowGuideItem[] }) {
  if (guides.length === 0) return null;

  return (
    <div
      className="scroll-mt-6 space-y-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70"
      id="dossier-sector-workflow-guide"
      tabIndex={-1}
    >
      <div>
        <h3 className="text-base font-semibold text-foreground">Sector workflow guide</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Retained sector modules are bounded checks. Use explicit sector hints and identifiers to rerun them.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-[repeat(2,minmax(0,1fr))]">
        {guides.map((guide) => (
          <article className="min-w-0 rounded-lg border border-border bg-card p-3 shadow-sm sm:p-4" key={guide.sector}>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <h4 className="min-w-0 break-words font-semibold text-foreground">{guide.label}</h4>
              <span className="max-w-full break-all rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {guide.retainedModules.map((module) => BUSINESS_MODULE_LABELS[module]).join(", ")}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{guide.whyRelevant}</p>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground">Required identifiers</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-sm leading-6 text-muted-foreground">
                  {guide.requiredIdentifiers.map((identifier) => <li key={identifier}>{identifier}</li>)}
                </ul>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground">Follow-up prompts</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-sm leading-6 text-muted-foreground">
                  {guide.followUpPrompts.map((prompt) => <li key={prompt}>{prompt}</li>)}
                </ul>
              </div>
            </div>
            <p className="mt-3 rounded-md bg-muted/60 p-2 text-xs leading-5 text-muted-foreground">
              {guide.sourceBoundUse}
            </p>
            <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
              {guide.retainedTools.join(", ")}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}

function ModuleStatusCard({
  defaultFollowUpValue,
  gaps,
  isRunning = false,
  onModuleFollowUp,
  reason,
  sectorGuide,
}: {
  defaultFollowUpValue: string;
  gaps: EvidenceGap[];
  isRunning?: boolean;
  onModuleFollowUp?: (request: ModuleFollowUpRequest) => void;
  reason: BusinessDossierModuleReason;
  sectorGuide?: SectorWorkflowGuideItem;
}) {
  const status = moduleStatus(reason, gaps);
  const followUpModule = reason.module === "acra" ? null : reason.module;
  const showFollowUp = followUpModule !== null
    && onModuleFollowUp !== undefined
    && (reason.status === "skipped" || reason.status === "unsearched" || reason.status === "needs_identifier" || reason.status === "unmatched");

  return (
    <article className={`min-w-0 rounded-lg border p-3 text-sm shadow-sm sm:p-4 ${status.className}`}>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <h4 className="min-w-0 break-words font-semibold">{BUSINESS_MODULE_LABELS[reason.module]}</h4>
        <span className="w-fit shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs font-medium uppercase text-muted-foreground">
          {status.label}
        </span>
      </div>
      <p className="mt-2 break-words text-xs text-muted-foreground">
        Selected by: {selectionReasonText(reason)}
      </p>
      <p className="mt-2 break-words leading-6">{reason.reason}</p>
      {reason.inferredSectors !== undefined && reason.inferredSectors.length > 0 ? (
        <p className="mt-2 break-words text-xs text-muted-foreground">
          Inferred: {reason.inferredSectors.map(formatLabel).join(", ")}
        </p>
      ) : null}
      {reason.webSectorHints !== undefined && reason.webSectorHints.length > 0 ? (
        <p className="mt-2 break-words text-xs text-muted-foreground">
          Web hint: {reason.webSectorHints.map(formatLabel).join(", ")}
        </p>
      ) : null}
      {sectorGuide === undefined ? null : (
        <div className="mt-3 grid gap-3 rounded-md bg-background/70 p-3 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Required identifiers</p>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground">
              {sectorGuide.requiredIdentifiers.map((identifier) => <li key={identifier}>{identifier}</li>)}
            </ul>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Next prompts</p>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground">
              {sectorGuide.followUpPrompts.map((prompt) => <li key={prompt}>{prompt}</li>)}
            </ul>
          </div>
        </div>
      )}
      {gaps.length > 0 ? (
        <div className="mt-3 space-y-2">
          {gaps.map((gap) => (
            <p className="break-words rounded-md bg-background/70 p-2 font-mono text-xs leading-5" key={`${gap.code}-${gap.message}`}>
              {gap.code}: <span className="font-sans">{gap.message}</span>
            </p>
          ))}
        </div>
      ) : null}
      {showFollowUp ? (
        <ModuleFollowUpForm
          defaultValue={defaultFollowUpValue}
          isRunning={isRunning}
          module={followUpModule}
          onModuleFollowUp={onModuleFollowUp}
        />
      ) : null}
    </article>
  );
}

function ModuleFollowUpForm({
  defaultValue,
  isRunning,
  module,
  onModuleFollowUp,
}: {
  defaultValue: string;
  isRunning: boolean;
  module: FollowUpBusinessModule;
  onModuleFollowUp: (request: ModuleFollowUpRequest) => void;
}) {
  const config = BUSINESS_MODULE_FOLLOW_UPS[module];
  const [value, setValue] = useState(defaultValue);
  const [error, setError] = useState<string | null>(null);
  const loadingTasks: AgentPlanTask[] = [
    {
      id: `${module}-follow-up`,
      title: `Run ${BUSINESS_MODULE_LABELS[module]} follow-up`,
      description: "Refresh the dossier with explicit sector context or identifiers.",
      status: "in-progress",
      priority: "high",
      subtasks: [
        {
          id: "build-input",
          title: "Build follow-up request",
          description: "Attach the current dossier, selected module, and analyst-supplied lookup value.",
          status: "completed",
          priority: "high",
          tools: ["dude-web"],
        },
        {
          id: "call-dossier",
          title: "Rerun CDD orchestrator",
          description: "Refresh ACRA-gated sector evidence, supplemental review, memo state, gaps, and provenance.",
          status: "in-progress",
          priority: "high",
          tools: ["cdd-orchestrator"],
        },
      ],
    },
  ];

  useEffect(() => {
    setValue(defaultValue);
  }, [defaultValue]);

  return (
    <form
      className="mt-4 space-y-2 rounded-md border border-border bg-background/80 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = value.trim();
        if (trimmed === "") {
          setError("Enter the sector identifier or name needed for this lookup.");
          return;
        }
        setError(null);
        onModuleFollowUp({ module, value: trimmed });
      }}
    >
      <div className="space-y-1">
        <label className="text-xs font-medium text-foreground" htmlFor={`module-follow-up-${module}`}>
          {config.inputLabel}
        </label>
        <p className="text-xs leading-5 text-muted-foreground">{config.helperText}</p>
      </div>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
        <Input
          aria-label={`${BUSINESS_MODULE_LABELS[module]} follow-up input`}
          className="min-w-0"
          disabled={isRunning}
          id={`module-follow-up-${module}`}
          onChange={(event) => setValue(event.target.value)}
          placeholder={config.placeholder}
          value={value}
        />
        <Button className="shrink-0" disabled={isRunning} size="sm" type="submit" variant="outline">
          {isRunning ? "Running" : `Run ${BUSINESS_MODULE_LABELS[module]} follow-up`}
        </Button>
      </div>
      {error === null ? null : <p className="text-xs text-destructive">{error}</p>}
      {isRunning ? (
        <AgentPlan
          className="mt-3"
          description="Dude is calling the selected official module and refreshing the dossier."
          tasks={loadingTasks}
          title="Dude is rerunning this check"
        />
      ) : null}
    </form>
  );
}

export function EvidenceSection({
  dossier,
  onModuleFollowUp,
  runningModule = null,
}: {
  dossier: BusinessDossier;
  onModuleFollowUp?: (request: ModuleFollowUpRequest) => void;
  runningModule?: RunningBusinessModule;
}) {
  const groups = getDossierRecordGroups(dossier);
  const sourceCoverage = getSourceCoverage(dossier);
  const moduleReasons = dossier.records.resolution?.moduleReasons ?? [];
  const sectorWorkflowGuide = dossier.records.resolution?.sectorWorkflowGuide ?? [];
  const defaultFollowUpValue = getSummaryString(dossier, "Entity")
    ?? getSummaryString(dossier, "UEN")
    ?? dossier.title;
  const unavailableModules = new Set(
    dossier.gaps
      .filter(isUnavailableGap)
      .map(getGapModule)
      .filter((module): module is BusinessDossierModule => module !== null),
  );
  const searchedReasons = moduleReasons.filter((item) => item.searched || unavailableModules.has(item.module));
  const notSearchedReasons = moduleReasons.filter((item) => !item.searched && !unavailableModules.has(item.module));
  const notSearchedFollowUpModules = Array.from(new Set(notSearchedReasons
    .map((item) => item.module)
    .filter((module): module is FollowUpBusinessModule => ALL_FOLLOW_UP_BUSINESS_MODULES.includes(module as FollowUpBusinessModule))));
  const groupsWithRecords = groups
    .map((group) => ({
      ...group,
      tables: group.tables.filter((table) => table.records.length > 0),
    }))
    .filter((group) => group.tables.length > 0);

  return (
    <section className="min-w-0 space-y-4">
      <div>
        <h2 className="text-xl font-semibold tracking-normal text-foreground">Evidence</h2>
      </div>

      <SectorWorkflowGuide guides={sectorWorkflowGuide} />

      {sourceCoverage.length > 0 ? (
        <div
          className="scroll-mt-6 space-y-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70"
          id="dossier-source-coverage"
          tabIndex={-1}
        >
          <div>
            <h3 className="text-base font-semibold text-foreground">Source coverage</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-[repeat(2,minmax(0,1fr))]">
            {sourceCoverage.map((item) => (
              <article className="min-w-0 rounded-lg border border-border bg-card p-3 shadow-sm sm:p-4" key={item.family}>
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <h4 className="min-w-0 break-words font-semibold text-foreground">{item.label}</h4>
                  <span className={`w-fit shrink-0 rounded-md border px-2 py-0.5 text-xs font-medium uppercase ${coverageStatusClassName(item.status)}`}>
                    {sourceCoverageStatusLabel(item.status)}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">
                    {sourceCoverageLevelLabel(item.coverageLevel)} coverage
                  </span>
                  <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">
                    {item.recordCount} record{item.recordCount === 1 ? "" : "s"}
                  </span>
                  <span className="max-w-full break-all rounded-md bg-muted px-2 py-1 text-muted-foreground">
                    {item.tools.join(", ")}
                  </span>
                </div>
                <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{item.reason}</p>
                {item.gapCodes === undefined || item.gapCodes.length === 0 ? null : (
                  <p className="mt-2 break-words rounded-md bg-background/70 p-2 font-mono text-xs leading-5 text-muted-foreground">
                    {item.gapCodes.join(", ")}
                  </p>
                )}
              </article>
            ))}
          </div>
        </div>
      ) : null}

      <dl
        className="grid scroll-mt-6 gap-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70 sm:grid-cols-[repeat(3,minmax(0,1fr))]"
        id="dossier-evidence-metrics"
        tabIndex={-1}
      >
        {dossier.evidence.map((item) => (
          <div className="min-w-0 rounded-lg border border-border bg-card p-3" key={`${item.label}-${item.source ?? ""}`}>
            <dt className="text-xs font-medium uppercase text-muted-foreground">{item.label}</dt>
            <dd className="mt-1 break-words text-sm text-foreground">{formatRecordValue(item.label, item.value)}</dd>
            {item.source !== undefined && item.source !== null ? (
              <dd className="mt-1 break-words text-xs text-muted-foreground">Source: {item.source}</dd>
            ) : null}
          </div>
        ))}
      </dl>

      {searchedReasons.length > 0 ? (
        <div
          className="scroll-mt-6 space-y-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70"
          id="dossier-evidence-searched"
          tabIndex={-1}
        >
          <div>
            <h3 className="text-base font-semibold text-foreground">Searched modules</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              These official sources were queried. Zero-match results are separate from unavailable upstreams.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-[repeat(2,minmax(0,1fr))]">
            {searchedReasons.map((item) => (
              <ModuleStatusCard
                defaultFollowUpValue={defaultFollowUpValue}
                gaps={moduleGaps(item.module, dossier.gaps)}
                isRunning={runningModule === item.module || runningModule === "all"}
                key={item.module}
                onModuleFollowUp={onModuleFollowUp}
                reason={item}
                sectorGuide={guideForModule(sectorWorkflowGuide, item.module)}
              />
            ))}
          </div>
        </div>
      ) : null}

      {notSearchedReasons.length > 0 ? (
        <div
          className="scroll-mt-6 space-y-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70"
          id="dossier-evidence-not-searched"
          tabIndex={-1}
        >
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-foreground">Not searched</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                These modules were outside this dossier scope or lacked the identifiers needed for lookup.
              </p>
            </div>
            {onModuleFollowUp === undefined || notSearchedFollowUpModules.length === 0 ? null : (
              <Button
                className="w-fit shrink-0"
                disabled={runningModule !== null}
                onClick={() => onModuleFollowUp({
                  kind: "all",
                  modules: notSearchedFollowUpModules,
                  value: defaultFollowUpValue,
                })}
                size="sm"
                type="button"
                variant="outline"
              >
                {runningModule === "all" ? "Running all checks" : "Run all available checks"}
              </Button>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-[repeat(2,minmax(0,1fr))]">
            {notSearchedReasons.map((item) => (
              <ModuleStatusCard
                defaultFollowUpValue={defaultFollowUpValue}
                gaps={moduleGaps(item.module, dossier.gaps)}
                isRunning={runningModule === item.module || runningModule === "all"}
                key={item.module}
                onModuleFollowUp={onModuleFollowUp}
                reason={item}
                sectorGuide={guideForModule(sectorWorkflowGuide, item.module)}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div
        className="scroll-mt-6 space-y-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring/70"
        id="dossier-evidence-records"
        tabIndex={-1}
      >
        <div>
          <h3 className="text-base font-semibold text-foreground">Matched records</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Records are shown only for modules that returned public data.
          </p>
        </div>

        {groupsWithRecords.length === 0 ? (
          <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
            No matched registry rows to display.
          </p>
        ) : (
          <div className="grid min-w-0 gap-4">
            {groupsWithRecords.map((group) => (
              <article className="min-w-0 overflow-hidden rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5" key={group.module}>
                <div className="mb-4 flex min-w-0 items-center justify-between gap-3">
                  <h4 className="text-base font-semibold text-foreground">{group.label}</h4>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {group.tables.reduce((count, table) => count + table.records.length, 0)} records
                  </span>
                </div>

                <div className="min-w-0 space-y-5">
                  {group.tables.map((table) => (
                    <div className="min-w-0 space-y-2" key={table.label}>
                      <h5 className="text-sm font-medium text-muted-foreground">{table.label}</h5>
                      <RecordTable records={table.records} />
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
