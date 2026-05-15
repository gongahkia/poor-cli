import type { BusinessDossier } from "@/types/dossier";

type GapKind = "rate_limited" | "unavailable" | "no_match" | "partial";

function gapKind(code: string, message: string): GapKind {
  const normalized = `${code} ${message}`.toLowerCase();
  if (normalized.includes("rate limit") || normalized.includes("429")) {
    return "rate_limited";
  }
  if (/UNAVAILABLE|FAILED|TIMEOUT/.test(code)) {
    return "unavailable";
  }
  if (code.includes("NO_MATCH")) {
    return "no_match";
  }
  return "partial";
}

function gapState(code: string, message: string): string {
  const kind = gapKind(code, message);
  if (kind === "rate_limited") return "data.gov.sg rate-limited";
  if (kind === "unavailable") return "official source unavailable";
  if (kind === "no_match") return "no official match";
  return "partial coverage";
}

function gapClassName(code: string, message: string): string {
  const kind = gapKind(code, message);
  if (kind === "rate_limited" || kind === "unavailable") {
    return "border-destructive/30 bg-destructive/5";
  }
  if (kind === "no_match") {
    return "border-border bg-background";
  }
  return "border-border bg-muted/40";
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
            <li className={`rounded-md border p-3 ${gapClassName(gap.code, gap.message)}`} key={`${gap.code}-${gap.message}`}>
              <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <p className="font-mono text-xs text-muted-foreground">{gap.code}</p>
                <span className={gapKind(gap.code, gap.message) === "unavailable" ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
                  {gapState(gap.code, gap.message)}
                </span>
              </div>
              <p className="mt-1 text-sm leading-6 text-foreground">{gap.message}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
