import { useState } from "react";

import {
  formatNextCheckInputLabel,
  formatNextCheckInputValue,
  getNextCheckInputEntries,
} from "@/lib/next-checks";
import { cn } from "@/lib/utils";
import type { BusinessDossier } from "@/types/dossier";

export function NextChecksSection({ dossier }: { dossier: BusinessDossier }) {
  const checks = dossier.nextChecks ?? [];
  const [reviewedItemIds, setReviewedItemIds] = useState<Set<string>>(() => new Set());

  const toggleReviewed = (id: string) => {
    setReviewedItemIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-muted-foreground">Dossier follow-up</p>
          <h2 className="mt-1 text-xl font-semibold tracking-normal text-foreground">What To Check Next</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Operational follow-ups generated from the dossier. Mark items reviewed as you complete or assign them.
          </p>
        </div>
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
        <div className="mt-4 grid gap-3">
          {checks.map((check, index) => {
            const inputEntries = getNextCheckInputEntries(check.input);
            const todoNumber = String(index + 1).padStart(2, "0");
            const itemId = `${check.tool}-${index}`;
            const isReviewed = reviewedItemIds.has(itemId);
            const reviewedTextClassName = isReviewed
              ? "text-muted-foreground line-through decoration-muted-foreground/70 decoration-2"
              : "text-foreground";
            const reviewedMutedTextClassName = isReviewed
              ? "text-muted-foreground/80 line-through decoration-muted-foreground/70 decoration-2"
              : "text-muted-foreground";

            return (
              <article
                className={cn(
                  "min-w-0 rounded-md border border-border p-3 transition-colors sm:p-4",
                  isReviewed && "border-border/70 bg-muted/30",
                )}
                data-reviewed={isReviewed ? "true" : "false"}
                key={itemId}
              >
                <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">To-do {todoNumber}</p>
                    <h3 className={cn("mt-1 break-words text-base font-semibold", reviewedTextClassName)}>
                      {check.reason}
                    </h3>
                  </div>
                  <span
                    className={cn(
                      "w-fit shrink-0 rounded-md bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900",
                      isReviewed && "opacity-70",
                    )}
                  >
                    Pending
                  </span>
                </div>

                <label className="mt-3 flex w-fit items-center gap-2 text-sm text-foreground">
                  <input
                    checked={isReviewed}
                    className="h-4 w-4 rounded border-border accent-slate-700"
                    onChange={() => toggleReviewed(itemId)}
                    type="checkbox"
                  />
                  Reviewed by analyst
                </label>

                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Inputs</p>
                    {inputEntries.length === 0 ? (
                      <p className={cn("mt-2 text-sm leading-6", reviewedMutedTextClassName)}>
                        No suggested input was returned.
                      </p>
                    ) : (
                      <dl className="mt-2 grid gap-2">
                        {inputEntries.map(([key, value]) => (
                          <div className="min-w-0" key={key}>
                            <dt className="text-xs font-semibold uppercase text-muted-foreground">
                              {formatNextCheckInputLabel(key)}
                            </dt>
                            <dd className={cn("mt-1 break-words text-sm leading-6", reviewedTextClassName)}>
                              {formatNextCheckInputValue(value)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Tool</p>
                    <p className={cn("mt-2 break-all font-mono text-sm leading-6", reviewedMutedTextClassName)}>
                      {check.tool}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Outcome</p>
                    <p className={cn("mt-2 break-words text-sm leading-6", reviewedMutedTextClassName)}>
                      Add any returned evidence, gaps, provenance, and freshness back to the dossier.
                    </p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
