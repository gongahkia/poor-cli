import type { BusinessDossier } from "@/types/dossier";

export function NextChecksSection({ dossier }: { dossier: BusinessDossier }) {
  const checks = dossier.nextChecks ?? [];

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">What To Check Next</h2>
      {checks.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          No follow-up checks were returned by the resolver.
        </p>
      ) : (
        <ol className="mt-4 space-y-3">
          {checks.map((check, index) => (
            <li className="rounded-md border border-border p-3" key={`${check.tool}-${index}`}>
              <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <h3 className="text-sm font-medium text-foreground">{check.reason}</h3>
                <span className="font-mono text-xs text-muted-foreground">{check.tool}</span>
              </div>
              <p className="mt-2 truncate font-mono text-xs text-muted-foreground" title={JSON.stringify(check.input)}>
                {JSON.stringify(check.input)}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
