import { describe, expect, it } from "vitest";

import {
  buildBusinessDossierInput,
  buildBusinessDossierExpandedInput,
  buildBusinessDossierFollowUpInput,
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

  it("builds bounded sector-module follow-up inputs", () => {
    expect(buildBusinessDossierFollowUpInput({
      dossier,
      identifier: "03591300B",
      module: "bca",
      value: "Example Builders Pte Ltd",
    })).toMatchObject({
      analystRerun: true,
      entityName: "Example Builders Pte Ltd",
      modules: ["acra", "bca"],
      sectorHints: ["construction"],
      uen: "03591300B",
    });

    expect(buildBusinessDossierFollowUpInput({
      dossier,
      identifier: "DBS BANK LTD",
      module: "cea",
      value: "L3000001A",
    })).toMatchObject({
      analystRerun: true,
      estateAgentLicenseNo: "L3000001A",
      modules: ["acra", "cea"],
      sectorHints: ["real_estate"],
    });

    expect(() => buildBusinessDossierFollowUpInput({
      dossier,
      identifier: "DBS BANK LTD",
      module: "hsa",
      value: " ",
    })).toThrow("Follow-up input is required.");
  });

  it("builds an expanded module rerun input with CEA company-name mapping", () => {
    expect(buildBusinessDossierExpandedInput({
      dossier,
      identifier: "03591300B",
      modules: ["bca", "cea", "gebiz"],
      value: "DBS BANK LTD",
    })).toMatchObject({
      analystRerun: true,
      entityName: "DBS BANK LTD",
      estateAgentName: "DBS BANK LTD",
      modules: ["acra", "bca", "cea", "gebiz"],
      sectorHints: ["construction", "real_estate", "procurement"],
      uen: "03591300B",
    });
  });

  it("maps BCA follow-up identifiers to class code, workhead, and grade inputs", () => {
    expect(buildBusinessDossierFollowUpInput({
      dossier,
      identifier: "DBS BANK LTD",
      module: "bca",
      value: "GB1",
    })).toMatchObject({
      analystRerun: true,
      classCode: "GB1",
      modules: ["acra", "bca"],
      sectorHints: ["construction"],
    });

    expect(buildBusinessDossierFollowUpInput({
      dossier,
      identifier: "DBS BANK LTD",
      module: "bca",
      value: "CW01 B2",
    })).toMatchObject({
      analystRerun: true,
      grade: "B2",
      modules: ["acra", "bca"],
      sectorHints: ["construction"],
      workhead: "CW01",
    });
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
