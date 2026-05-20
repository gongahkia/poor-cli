import { getSummaryString } from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

export type EntityLogo = {
  alt: string;
  imageUrl: string;
  sourceUrl: string;
};

const KNOWN_ENTITY_LOGOS: readonly {
  imageUrl: string;
  match: RegExp;
  name: string;
  sourceUrl: string;
}[] = [
  {
    imageUrl: "https://logos-world.net/wp-content/uploads/2023/04/DBS-Logo.png",
    match: /\bDBS\b/i,
    name: "DBS",
    sourceUrl: "https://logos-world.net/dbs-logo/",
  },
];

const initialsFromName = (name: string): string => {
  const words = name
    .replace(/[^a-z0-9\s]/gi, " ")
    .split(/\s+/)
    .filter(Boolean)
    .filter((word) => !["pte", "ltd", "limited", "llp", "plc", "inc"].includes(word.toLowerCase()));

  const initials = words.slice(0, 2).map((word) => word[0]?.toUpperCase() ?? "").join("");
  return initials || "SG";
};

export function getDossierEntityName(dossier: BusinessDossier): string {
  return getSummaryString(dossier, "Entity") ?? dossier.title;
}

export function getDossierEntityInitials(dossier: BusinessDossier): string {
  return initialsFromName(getDossierEntityName(dossier));
}

export function resolveDossierEntityLogo(dossier: BusinessDossier): EntityLogo | null {
  const entityName = getDossierEntityName(dossier);
  const match = KNOWN_ENTITY_LOGOS.find((item) => item.match.test(entityName));
  if (match === undefined) {
    return null;
  }

  return {
    alt: `${match.name} logo`,
    imageUrl: match.imageUrl,
    sourceUrl: match.sourceUrl,
  };
}
