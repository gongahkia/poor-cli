import type { BusinessDossier } from "@/types/dossier";

export function LimitsSection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <h2 className="text-base font-semibold text-foreground">What this does not do</h2>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
        {dossier.limits.map((limit) => (
          <li key={`${limit.code}-${limit.message}`}>
            <span className="font-mono text-xs text-foreground">{limit.code}</span>: {limit.message}
          </li>
        ))}
      </ul>
    </section>
  );
}
