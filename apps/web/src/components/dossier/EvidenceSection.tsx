import { RecordTable } from "@/components/dossier/RecordTable";
import { BUSINESS_MODULE_LABELS, formatLabel, formatRecordValue } from "@/lib/dossier";
import { getDossierRecordGroups } from "@/lib/dossier";
import type {
  BusinessDossier,
  BusinessDossierModule,
  BusinessDossierModuleReason,
  EvidenceGap,
} from "@/types/dossier";

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
  gaps,
  reason,
}: {
  gaps: EvidenceGap[];
  reason: BusinessDossierModuleReason;
}) {
  const status = moduleStatus(reason, gaps);

  return (
    <article className={`rounded-lg border p-4 text-sm shadow-sm ${status.className}`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <h4 className="font-semibold">{BUSINESS_MODULE_LABELS[reason.module]}</h4>
        <span className="w-fit rounded-md bg-muted px-2 py-0.5 text-xs font-medium uppercase text-muted-foreground">
          {status.label}
        </span>
      </div>
      <p className="mt-2 leading-6">{reason.reason}</p>
      {reason.inferredSectors !== undefined && reason.inferredSectors.length > 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Inferred: {reason.inferredSectors.map(formatLabel).join(", ")}
        </p>
      ) : null}
      {gaps.length > 0 ? (
        <div className="mt-3 space-y-2">
          {gaps.map((gap) => (
            <p className="rounded-md bg-background/70 p-2 font-mono text-xs leading-5" key={`${gap.code}-${gap.message}`}>
              {gap.code}: <span className="font-sans">{gap.message}</span>
            </p>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function EvidenceSection({ dossier }: { dossier: BusinessDossier }) {
  const groups = getDossierRecordGroups(dossier);
  const moduleReasons = dossier.records.resolution?.moduleReasons ?? [];
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
    <section className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold tracking-normal text-foreground">Evidence</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Public registry records grouped by modules that were actually searched. Skipped modules remain available for explicit sector checks.
        </p>
      </div>

      <dl className="grid gap-3 sm:grid-cols-3">
        {dossier.evidence.map((item) => (
          <div className="rounded-lg border border-border bg-card p-3" key={`${item.label}-${item.source ?? ""}`}>
            <dt className="text-xs font-medium uppercase text-muted-foreground">{item.label}</dt>
            <dd className="mt-1 text-sm text-foreground">{formatRecordValue(item.label, item.value)}</dd>
            {item.source !== undefined && item.source !== null ? (
              <dd className="mt-1 text-xs text-muted-foreground">Source: {item.source}</dd>
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
          <div className="grid gap-3 md:grid-cols-2">
            {searchedReasons.map((item) => (
              <ModuleStatusCard gaps={moduleGaps(item.module, dossier.gaps)} key={item.module} reason={item} />
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
          <div className="grid gap-3 md:grid-cols-2">
            {notSearchedReasons.map((item) => (
              <ModuleStatusCard gaps={[]} key={item.module} reason={item} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-3">
        <div>
          <h3 className="text-base font-semibold text-foreground">Matched records</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Tables are shown only for modules that returned public records.
          </p>
        </div>

        {groupsWithRecords.length === 0 ? (
          <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
            No matched registry rows to display.
          </p>
        ) : (
          <div className="grid gap-4">
            {groupsWithRecords.map((group) => (
              <article className="rounded-lg border border-border bg-card p-5 shadow-sm" key={group.module}>
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h4 className="text-base font-semibold text-foreground">{group.label}</h4>
                  <span className="text-xs text-muted-foreground">
                    {group.tables.reduce((count, table) => count + table.records.length, 0)} records
                  </span>
                </div>

                <div className="space-y-5">
                  {group.tables.map((table) => (
                    <div className="space-y-2" key={table.label}>
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
