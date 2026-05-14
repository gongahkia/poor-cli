import { RecordTable } from "@/components/dossier/RecordTable";
import { formatRecordValue } from "@/lib/dossier";
import { getDossierRecordGroups } from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

export function EvidenceSection({ dossier }: { dossier: BusinessDossier }) {
  const groups = getDossierRecordGroups(dossier);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold tracking-normal text-foreground">Evidence</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Public registry records grouped by source module.
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

      <div className="grid gap-4">
        {groups.map((group) => (
          <article className="rounded-lg border border-border bg-card p-5 shadow-sm" key={group.module}>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-base font-semibold text-foreground">{group.label}</h3>
              <span className="text-xs text-muted-foreground">
                {group.tables.reduce((count, table) => count + table.records.length, 0)} records
              </span>
            </div>

            <div className="space-y-5">
              {group.tables.map((table) => (
                <div className="space-y-2" key={table.label}>
                  <h4 className="text-sm font-medium text-muted-foreground">{table.label}</h4>
                  <RecordTable records={table.records} />
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
