import { useMemo, useState } from "react";

import {
  buildPdpaChecklist,
  pdpaStatusLabel,
  type PdpaChecklistStatus,
} from "@/lib/pdpa";
import type { BusinessDossier } from "@/types/dossier";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type PdpaChecklistSectionProps = {
  dossier: BusinessDossier;
  isExporting?: boolean;
  onExportReport?: (reviewedItemIds: readonly string[]) => void;
};

const statusClassName = (status: PdpaChecklistStatus): string => {
  if (status === "evidence_available") {
    return "bg-emerald-50 text-emerald-900";
  }
  if (status === "blocked_by_gap") {
    return "bg-destructive/10 text-destructive";
  }
  return "bg-amber-50 text-amber-900";
};

export function PdpaChecklistSection({
  dossier,
  isExporting = false,
  onExportReport,
}: PdpaChecklistSectionProps) {
  const items = useMemo(() => buildPdpaChecklist(dossier), [dossier]);
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
          <p className="text-sm font-medium text-muted-foreground">PDPA vendor diligence</p>
          <h2 className="mt-1 text-xl font-semibold tracking-normal text-foreground">Checklist</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Evidence is tied to dossier provenance, freshness, gaps, and limits. This is not legal advice or a compliance opinion.
          </p>
        </div>
        {onExportReport === undefined ? null : (
          <Button
            disabled={isExporting}
            onClick={() => onExportReport(Array.from(reviewedItemIds))}
            type="button"
            variant="outline"
          >
            {isExporting ? "Exporting" : "Export PDPA report"}
          </Button>
        )}
      </div>

      <div className="mt-4 grid gap-3">
        {items.map((item) => {
          const isReviewed = reviewedItemIds.has(item.id);
          const reviewedTextClassName = isReviewed
            ? "text-muted-foreground line-through decoration-muted-foreground/70 decoration-2"
            : "text-foreground";
          const reviewedMutedTextClassName = isReviewed
            ? "text-muted-foreground/80 line-through decoration-muted-foreground/70 decoration-2"
            : "text-muted-foreground";

          return (
            <article
              className={cn(
                "min-w-0 rounded-md border border-border p-3 transition-colors",
                isReviewed && "border-border/70 bg-muted/30",
              )}
              data-reviewed={isReviewed ? "true" : "false"}
              key={item.id}
            >
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <h3 className={cn("break-words text-base font-semibold", reviewedTextClassName)}>{item.title}</h3>
                  <p className={cn("mt-1 text-sm", reviewedMutedTextClassName)}>{item.obligation}</p>
                </div>
                <span
                  className={cn(
                    "w-fit shrink-0 rounded-md px-2.5 py-1 text-xs font-medium",
                    statusClassName(item.status),
                    isReviewed && "opacity-70",
                  )}
                >
                  {pdpaStatusLabel(item.status)}
                </span>
              </div>

              <label className="mt-3 flex w-fit items-center gap-2 text-sm text-foreground">
                <input
                  checked={isReviewed}
                  className="h-4 w-4 rounded border-border"
                  onChange={() => toggleReviewed(item.id)}
                  type="checkbox"
                />
                Reviewed by analyst
              </label>

              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Evidence</p>
                  <ul className={cn("mt-2 space-y-1 text-sm leading-6", reviewedTextClassName)}>
                    {item.evidence.slice(0, 4).map((line) => (
                      <li className="break-words" key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Gaps</p>
                  <ul className={cn("mt-2 space-y-1 text-sm leading-6", reviewedMutedTextClassName)}>
                    {item.gaps.slice(0, 4).map((line) => (
                      <li className="break-words" key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Action</p>
                  <p className={cn("mt-2 break-words text-sm leading-6", reviewedTextClassName)}>{item.action}</p>
                  <p className={cn("mt-2 break-words text-xs leading-5", reviewedMutedTextClassName)}>
                    {item.citations.map((citation) => citation.id).join(", ")}
                  </p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
