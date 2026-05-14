import { confidenceLabel, getDossierConfidence } from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

export function ConfidenceSection({ dossier }: { dossier: BusinessDossier }) {
  const confidence = getDossierConfidence(dossier);
  const matches = dossier.matchConfidence ?? [];

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Match Confidence</h2>
      {confidence !== null ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {confidence.level.toUpperCase()}
          {confidence.score === undefined ? "" : ` · ${Math.round(confidence.score * 100)}%`}{" "}
          {confidence.rationale ?? ""}
        </p>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No confidence summary was returned.</p>
      )}

      {matches.length > 0 ? (
        <div className="mt-4 grid gap-2">
          {matches.map((match) => (
            <div
              className="flex flex-col gap-1 rounded-md border border-border p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
              key={`${match.source}-${match.matchedOn ?? "none"}`}
            >
              <span className="font-medium text-foreground">{match.source}</span>
              <span className="text-muted-foreground">
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
