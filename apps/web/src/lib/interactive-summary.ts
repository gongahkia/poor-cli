import { getSummaryString } from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";
import type { InteractiveSummarySegment } from "@/types/interactive-summary";

export function buildFallbackInteractiveSummary(dossier: BusinessDossier): InteractiveSummarySegment[] {
  const entity = getSummaryString(dossier, "Entity") ?? dossier.title;
  const status = getSummaryString(dossier, "Entity status");
  const matchedModules = dossier.records.resolution?.matchedModules ?? [];
  const matchedModuleText = matchedModules.length > 0
    ? matchedModules.map((module) => module.toUpperCase()).join(", ")
    : "the returned public records";
  const riskCount = dossier.riskFlags?.length ?? 0;
  const riskText = riskCount > 0
    ? `${riskCount} risk signal${riskCount === 1 ? "" : "s"}`
    : "no returned risk flags";
  const gapText = dossier.gaps.length > 0
    ? `${dossier.gaps.length} evidence gap${dossier.gaps.length === 1 ? "" : "s"}`
    : "provenance and freshness notes";

  return [
    { emphasized: false, targetId: "overview.summary", text: "The dossier identifies " },
    { emphasized: true, targetId: "overview.summary", text: entity },
    ...(status === null ? [] : [
      { emphasized: false as const, targetId: "overview.summary" as const, text: " as " },
      { emphasized: true as const, targetId: "overview.snapshot" as const, text: status },
    ]),
    { emphasized: false, targetId: "evidence.records", text: " with " },
    { emphasized: true, targetId: "evidence.records", text: matchedModuleText },
    { emphasized: false, targetId: "overview.risk", text: ", " },
    { emphasized: true, targetId: "overview.risk", text: riskText },
    { emphasized: false, targetId: "audit.gaps", text: ", and " },
    { emphasized: true, targetId: dossier.gaps.length > 0 ? "audit.gaps" : "audit.provenance", text: gapText },
    { emphasized: false, targetId: "audit.provenance", text: "." },
  ];
}
