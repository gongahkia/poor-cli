import { Square } from "lucide-react";

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
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-semibold tracking-normal text-foreground">
          What To Check Next
        </h2>
        {checks.length > 0 ? (
          <span className="w-fit rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
            {checks.length} open {checks.length === 1 ? "todo" : "todos"}
          </span>
        ) : null}
      </div>
      {checks.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          No follow-up checks were returned by the resolver.
        </p>
      ) : (
        <ol className="mt-4 overflow-hidden rounded-lg border border-border">
          {checks.map((check, index) => {
            const inputEntries = getNextCheckInputEntries(check.input);
            const todoNumber = String(index + 1).padStart(2, "0");

            return (
              <li
                className="grid min-w-0 gap-3 border-b border-border bg-background p-4 last:border-b-0 sm:grid-cols-[auto_minmax(0,1fr)]"
                key={`${check.tool}-${index}`}
              >
                <div className="flex items-center gap-3 sm:flex-col sm:items-center">
                  <span
                    aria-hidden="true"
                    className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground"
                  >
                    <Square className="h-4 w-4" />
                  </span>
                  <span className="text-xs font-semibold uppercase text-muted-foreground">
                    {todoNumber}
                  </span>
                </div>

                <div className="min-w-0">
                  <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">
                        To-do {todoNumber}
                      </p>
                      <h3 className="mt-1 min-w-0 break-words text-base font-semibold text-foreground">
                        {check.reason}
                      </h3>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
                        Pending
                      </span>
                      <span className="rounded-md bg-muted px-2.5 py-1 font-mono text-xs text-muted-foreground">
                        {check.tool}
                      </span>
                    </div>
                  </div>

                  <div className="mt-4 rounded-lg bg-muted/25 p-3">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">
                      Inputs to use
                    </p>
                    {inputEntries.length === 0 ? (
                      <p className="mt-2 text-sm text-muted-foreground">
                        No suggested input was returned.
                      </p>
                    ) : (
                      <dl className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                        {inputEntries.map(([key, value]) => (
                          <div className="min-w-0 rounded-md bg-background px-3 py-2" key={key}>
                            <dt className="text-xs font-semibold uppercase text-muted-foreground">
                              {formatNextCheckInputLabel(key)}
                            </dt>
                            <dd className="mt-1 break-words text-sm text-foreground">
                              {formatNextCheckInputValue(value)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
