import { describe, expect, it } from "vitest";

import {
  buildBusinessDossierInput,
  buildDiligenceSnapshot,
  getSectorBadges,
  getSummaryString,
  isNotFoundDossier,
} from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [],
  freshness: [],
  gaps: [],
  limits: [],
  provenance: [],
  records: {
    acra: [{
      entityName: "DBS BANK LTD",
      entityStatusDescription: "Live",
      entityTypeDescription: "Local Company",
      postalCode: "018982",
      primarySsicCode: "64120",
      primarySsicDescription: "Full banks",
      registrationIncorporationDate: "1968-07-16",
      streetName: "Marina Boulevard",
      uen: "03591300B",
    }],
    resolution: {
      matchedModules: ["acra"],
      selectedModules: ["acra", "gebiz"],
    },
  },
  summary: [
    { label: "Entity", value: "DBS BANK LTD" },
    { label: "UEN", value: "03591300B" },
    { label: "Entity status", value: "Live" },
  ],
  title: "Business Dossier",
};

describe("dossier helpers", () => {
  it("detects UENs and entity-name inputs", () => {
    expect(buildBusinessDossierInput("03591300B")).toEqual({ uen: "03591300B" });
    expect(buildBusinessDossierInput("DBS BANK")).toEqual({ entityName: "DBS BANK" });
  });

  it("extracts summary and snapshot values", () => {
    expect(getSummaryString(dossier, "Entity")).toBe("DBS BANK LTD");
    expect(buildDiligenceSnapshot(dossier)).toMatchObject({
      entityName: "DBS BANK LTD",
      matchedModules: "acra",
      primarySsic: "64120 - Full banks",
    });
  });

  it("builds sector badges and not-found state", () => {
    expect(getSectorBadges(dossier)).toEqual(expect.arrayContaining(["finance", "procurement"]));
    expect(isNotFoundDossier(dossier)).toBe(false);
    expect(isNotFoundDossier({
      ...dossier,
      records: { resolution: { matchedModules: [] } },
    })).toBe(true);
  });
});
