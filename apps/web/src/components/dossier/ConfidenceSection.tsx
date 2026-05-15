import { confidenceLabel, getDossierConfidence } from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

export function ConfidenceSection({ dossier }: { dossier: BusinessDossier }) {
  const confidence = getDossierConfidence(dossier);
  const matches = dossier.matchConfidence ?? [];
  const coverage = confidence?.coverage;
  const matchedCount = coverage?.matchedModules?.length;
  const searchedCount = coverage?.searchedModules?.length;

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Match Confidence</h2>
      {confidence !== null ? (
        <div className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
          <p>
            Identity: {confidence.level.toUpperCase()}
            {confidence.score === undefined ? "" : ` · ${Math.round(confidence.score * 100)}%`}{" "}
            {confidence.rationale ?? ""}
          </p>
          {coverage !== undefined ? (
            <p>
              Coverage: {matchedCount ?? 0}/{searchedCount ?? 0} searched modules matched
              {coverage.unsearchedModules === undefined || coverage.unsearchedModules.length === 0
                ? "."
                : `; ${coverage.unsearchedModules.length} selected modules were not searched.`}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No confidence summary was returned.</p>
      )}

      {matches.length > 0 ? (
        <div className="mt-4 grid gap-2">
          {matches.map((match) => (
            <div
              className="flex min-w-0 flex-col gap-1 rounded-md border border-border p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
              key={`${match.source}-${match.matchedOn ?? "none"}`}
            >
              <span className="min-w-0 break-words font-medium text-foreground">{match.source}</span>
              <span className="break-words text-muted-foreground sm:text-right">
                {confidenceLabel(match.confidence)}
                {match.matchedOn === null ? "" : ` on ${match.matchedOn}`}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
