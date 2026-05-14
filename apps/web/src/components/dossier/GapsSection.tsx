import type { BusinessDossier } from "@/types/dossier";

function gapState(code: string, message: string): string {
  const normalized = `${code} ${message}`.toLowerCase();
  if (normalized.includes("rate limit") || normalized.includes("429")) {
    return "data.gov.sg rate-limited";
  }
  if (code.includes("UNAVAILABLE")) {
    return "official source unavailable";
  }
  if (code.includes("NO_MATCH")) {
    return "no official match";
  }
  return "partial coverage";
}

export function GapsSection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section className="rounded-lg border border-border bg-muted/30 p-5">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">What we couldn't find</h2>
      {dossier.gaps.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          No lookup gaps were returned by the selected modules.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {dossier.gaps.map((gap) => (
            <li className="rounded-md border border-border bg-background p-3" key={`${gap.code}-${gap.message}`}>
              <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <p className="font-mono text-xs text-muted-foreground">{gap.code}</p>
                <span className="text-xs text-muted-foreground">{gapState(gap.code, gap.message)}</span>
              </div>
              <p className="mt-1 text-sm leading-6 text-foreground">{gap.message}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
