import {
  formatNextCheckInputLabel,
  formatNextCheckInputValue,
  getNextCheckInputEntries,
} from "@/lib/next-checks";
import type { BusinessDossier } from "@/types/dossier";

export function NextChecksSection({ dossier }: { dossier: BusinessDossier }) {
  const checks = dossier.nextChecks ?? [];

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">What To Check Next</h2>
      {checks.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          No follow-up checks were returned by the resolver.
        </p>
      ) : (
        <ol className="mt-4 space-y-3">
          {checks.map((check, index) => {
            const inputEntries = getNextCheckInputEntries(check.input);

            return (
              <li className="min-w-0 rounded-md border border-border p-3" key={`${check.tool}-${index}`}>
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <h3 className="min-w-0 break-words text-sm font-medium text-foreground">{check.reason}</h3>
                  <span className="w-fit shrink-0 rounded-md bg-muted px-2.5 py-1 font-mono text-xs text-muted-foreground">
                    {check.tool}
                  </span>
                </div>

                {inputEntries.length === 0 ? (
                  <p className="mt-3 text-xs text-muted-foreground">No suggested input was returned.</p>
                ) : (
                  <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {inputEntries.map(([key, value]) => (
                      <div className="min-w-0 rounded-md bg-muted/40 px-3 py-2" key={key}>
                        <dt className="text-xs font-semibold uppercase text-muted-foreground">{formatNextCheckInputLabel(key)}</dt>
                        <dd className="mt-1 break-words text-sm text-foreground">{formatNextCheckInputValue(value)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
