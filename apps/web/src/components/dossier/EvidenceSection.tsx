import { useEffect, useState } from "react";

import { RecordTable } from "@/components/dossier/RecordTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  BUSINESS_MODULE_FOLLOW_UPS,
  BUSINESS_MODULE_LABELS,
  formatLabel,
  formatRecordValue,
  getDossierRecordGroups,
  getSummaryString,
  type FollowUpBusinessModule,
} from "@/lib/dossier";
import type {
  BusinessDossier,
  BusinessDossierModule,
  BusinessDossierModuleReason,
  EvidenceGap,
} from "@/types/dossier";

export type ModuleFollowUpRequest = {
  module: FollowUpBusinessModule;
  value: string;
};

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

function moduleStatus(
  reason: BusinessDossierModuleReason,
  gaps: EvidenceGap[],
): { label: string; className: string } {
  if (gaps.some(isUnavailableGap)) {
    return {
      label: "Source unavailable",
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
      label: "No official match",
      className: "border-border bg-muted/50 text-foreground",
    };
  }
  return {
    label: reason.status === "unsearched" ? "Not searched" : "Skipped",
    className: "border-border bg-background text-muted-foreground",
  };
}

function ModuleStatusCard({
  defaultFollowUpValue,
  gaps,
  isRunning = false,
  onModuleFollowUp,
  reason,
}: {
  defaultFollowUpValue: string;
  gaps: EvidenceGap[];
  isRunning?: boolean;
  onModuleFollowUp?: (request: ModuleFollowUpRequest) => void;
  reason: BusinessDossierModuleReason;
}) {
  const status = moduleStatus(reason, gaps);
  const followUpModule = reason.module === "acra" ? null : reason.module;
  const showFollowUp = followUpModule !== null
    && onModuleFollowUp !== undefined
    && (reason.status === "skipped" || reason.status === "unsearched");

  return (
    <article className={`min-w-0 rounded-lg border p-3 text-sm shadow-sm sm:p-4 ${status.className}`}>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <h4 className="min-w-0 break-words font-semibold">{BUSINESS_MODULE_LABELS[reason.module]}</h4>
        <span className="w-fit shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs font-medium uppercase text-muted-foreground">
          {status.label}
        </span>
      </div>
      <p className="mt-2 break-words leading-6">{reason.reason}</p>
      {reason.inferredSectors !== undefined && reason.inferredSectors.length > 0 ? (
        <p className="mt-2 break-words text-xs text-muted-foreground">
          Inferred: {reason.inferredSectors.map(formatLabel).join(", ")}
        </p>
      ) : null}
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
  runningModule?: BusinessDossierModule | null;
}) {
  const groups = getDossierRecordGroups(dossier);
  const moduleReasons = dossier.records.resolution?.moduleReasons ?? [];
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
        <p className="mt-1 text-sm text-muted-foreground">
          Public registry records grouped by modules that were actually searched. Skipped modules remain available for explicit sector checks.
        </p>
      </div>

      <dl className="grid gap-3 sm:grid-cols-[repeat(3,minmax(0,1fr))]">
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
        <div className="space-y-3">
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
                isRunning={runningModule === item.module}
                key={item.module}
                onModuleFollowUp={onModuleFollowUp}
                reason={item}
              />
            ))}
          </div>
        </div>
      ) : null}

      {notSearchedReasons.length > 0 ? (
        <div className="space-y-3">
          <div>
            <h3 className="text-base font-semibold text-foreground">Not searched</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              These modules were outside this dossier scope or lacked the identifiers needed for lookup.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-[repeat(2,minmax(0,1fr))]">
            {notSearchedReasons.map((item) => (
              <ModuleStatusCard
                defaultFollowUpValue={defaultFollowUpValue}
                gaps={moduleGaps(item.module, dossier.gaps)}
                isRunning={runningModule === item.module}
                key={item.module}
                onModuleFollowUp={onModuleFollowUp}
                reason={item}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-3">
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
