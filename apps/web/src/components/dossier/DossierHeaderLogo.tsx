import { useMemo, useState } from "react";

import {
  getDossierEntityInitials,
  getDossierEntityName,
  resolveDossierEntityLogo,
} from "@/lib/entity-logo";
import { cn } from "@/lib/utils";
import type { BusinessDossier } from "@/types/dossier";

export function DossierHeaderLogo({ dossier }: { dossier: BusinessDossier }) {
  const logo = useMemo(() => resolveDossierEntityLogo(dossier), [dossier]);
  const initials = useMemo(() => getDossierEntityInitials(dossier), [dossier]);
  const entityName = useMemo(() => getDossierEntityName(dossier), [dossier]);
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = logo !== null && !imageFailed;

  return (
    <div
      aria-label={`${entityName} brand mark`}
      className={cn(
        "flex h-20 w-32 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-card shadow-sm",
        showImage ? "p-3" : "bg-muted",
      )}
      title={logo === null ? entityName : `Logo source: ${logo.sourceUrl}`}
    >
      {showImage ? (
        <img
          alt={logo.alt}
          className="max-h-full max-w-full object-contain"
          decoding="async"
          height="80"
          loading="eager"
          onError={() => setImageFailed(true)}
          referrerPolicy="no-referrer"
          src={logo.imageUrl}
          width="128"
        />
      ) : (
        <span className="text-2xl font-semibold tracking-normal text-muted-foreground">{initials}</span>
      )}
    </div>
  );
}
