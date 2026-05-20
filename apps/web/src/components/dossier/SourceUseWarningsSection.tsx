import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";

import type { PeopleDiscovery, WebPresence } from "@/lib/api/client";
import { buildSourceUseWarnings } from "@/lib/source-use-warnings";
import type { BusinessDossier } from "@/types/dossier";

type SourceUseWarningsSectionProps = {
  dossier: BusinessDossier;
  peopleDiscovery?: PeopleDiscovery;
  webPresence?: WebPresence;
};

export function SourceUseWarningsSection({
  dossier,
  peopleDiscovery,
  webPresence,
}: SourceUseWarningsSectionProps) {
  const warnings = useMemo(
    () => buildSourceUseWarnings({ dossier, peopleDiscovery, webPresence }),
    [dossier, peopleDiscovery, webPresence],
  );

  if (warnings.length === 0) return null;

  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-950 shadow-sm sm:p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0">
          <h2 className="text-base font-semibold">Source-use warnings</h2>
          <p className="mt-1 text-sm leading-6 text-amber-900">
            These warnings are separate from risk findings and apply to how the cited evidence may be reused.
          </p>
          <ul className="mt-3 space-y-3 text-sm leading-6">
            {warnings.map((warning) => (
              <li className="break-words" key={warning.id}>
                <span className="block font-semibold">{warning.title}</span>
                <span className="mt-0.5 block">{warning.message}</span>
                <span className="mt-1 block text-xs text-amber-800">
                  Triggered by: {warning.triggeredBy.join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
