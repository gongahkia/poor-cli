import { riskSeverityLabel } from "@/lib/dossier";
import type { BusinessDossier, RiskFlag } from "@/types/dossier";

const severityClassName: Record<RiskFlag["severity"], string> = {
  high: "border-destructive/30 bg-destructive/5 text-destructive",
  medium: "border-border bg-muted/50 text-foreground",
  low: "border-border bg-card text-muted-foreground",
};

export function RiskSection({ dossier }: { dossier: BusinessDossier }) {
  const flags = dossier.riskFlags ?? [];

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Risk Signals</h2>
      {flags.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          No risk flags were returned by the selected modules.
        </p>
      ) : (
        <div className="mt-4 grid gap-3">
          {flags.map((flag) => (
            <article
              className={`min-w-0 rounded-md border p-3 ${severityClassName[flag.severity]}`}
              key={`${flag.code}-${flag.source}`}
            >
              <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <h3 className="break-words text-sm font-semibold">{flag.message}</h3>
                <span className="shrink-0 text-xs font-medium">{riskSeverityLabel(flag)}</span>
              </div>
              <p className="mt-2 break-words font-mono text-xs opacity-80">
                {flag.code} · {flag.source}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
