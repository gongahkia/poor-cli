import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BriefArtifactSchema } from "../index.js";

const readGolden = (name: string) => {
  const url = new URL(`./fixtures/golden/${name}`, import.meta.url);
  return JSON.parse(readFileSync(url, "utf8"));
};

describe("brief golden outputs", () => {
  it("keeps the business dossier golden believable", () => {
    const payload = BriefArtifactSchema.parse(readGolden("business-dossier.json"));
    const entityStatus = payload.summary.find((item) => item.label === "Entity status")?.value;

    expect(payload.title).toBe("Business Dossier");
    expect(entityStatus).toBe("Live Company");
    expect(payload.riskFlags ?? []).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ code: "ENTITY_NOT_ACTIVE" })]),
    );
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([expect.objectContaining({ source: "ACRA", confidence: "exact" })]),
    );
  });

  it("keeps the property brief golden location-aware and contract-correct", () => {
    const payload = BriefArtifactSchema.parse(readGolden("property-brief.json"));
    const locationResolution = payload.records["locationResolution"] as Record<string, unknown>;

    expect(payload.title).toBe("Property Brief");
    expect(locationResolution).toMatchObject({
      resolvedPlanningArea: "Bedok",
      resolvedRegion: "East",
      resolvedPostalCode: "460123",
    });
    expect(payload.nextChecks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          tool: "sg_ura_property_transactions",
          input: expect.objectContaining({ area: "Bedok" }),
        }),
      ]),
    );
  });

  it("keeps the macro brief golden metric-oriented", () => {
    const payload = BriefArtifactSchema.parse(readGolden("macro-brief.json"));
    const summaryLabels = new Set(payload.summary.map((item) => item.label));
    const kpis = payload.records["kpis"] as Record<string, unknown>;

    expect(payload.title).toBe("Macro Brief");
    expect(summaryLabels.has("SORA")).toBe(true);
    expect(summaryLabels.has("Total deposits")).toBe(true);
    expect(kpis).toMatchObject({
      singstatSeries: {
        gdpTableId: "M015631",
        cpiYoYTableId: "M213781",
        cpiIndexTableId: "M213751",
      },
    });
    expect(payload.summary.find((item) => item.label === "GDP table ID")?.value).not.toBe(
      payload.summary.find((item) => item.label === "CPI YoY table ID")?.value,
    );
  });

  it("keeps the transport brief golden operational", () => {
    const payload = BriefArtifactSchema.parse(readGolden("transport-brief.json"));
    const status = payload.records["status"] as Record<string, unknown>;

    expect(payload.title).toBe("Transport Brief");
    expect(status["level"]).toBe("advisory");
    expect(payload.records["followups"]).toBeDefined();
  });

  it("keeps the environment brief golden threshold-aware", () => {
    const payload = BriefArtifactSchema.parse(readGolden("environment-brief.json"));
    const thresholds = payload.records["thresholds"] as Record<string, unknown>;

    expect(payload.title).toBe("Environment Brief");
    expect(thresholds["advisory"]).toBe("Carry umbrella, monitor conditions");
    expect(thresholds["forecastRisk"]).toBe("watch");
  });
});
