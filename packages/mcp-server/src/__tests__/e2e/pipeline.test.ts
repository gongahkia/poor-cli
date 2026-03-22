import { describe, it, expect } from "vitest";
import { classifyIntent } from "../../router/classifier.js";
import { planQuery } from "../../router/planner.js";

describe("E2E Pipeline", () => {
  it("routes exchange rate query to MAS", () => {
    const intent = classifyIntent("What's the SGD to USD exchange rate?");
    expect(intent.intent).toBe("financial");
    expect(intent.tool).toBe("sg_mas_exchange_rates");
    expect(intent.apis).toContain("mas");
    expect(intent.extractedParams["currency"]).toBe("USD");
  });

  it("routes population query to OneMap", () => {
    const intent = classifyIntent("Population of Tampines");
    expect(intent.intent).toBe("demographic");
    expect(intent.tool).toBe("sg_onemap_population");
    expect(intent.apis).toContain("onemap");
    expect(intent.extractedParams["planningArea"]).toBe("Tampines");
  });

  it("routes GDP query to SingStat", () => {
    const intent = classifyIntent("Search for GDP datasets");
    expect(intent.intent).toBe("economic");
    expect(intent.tool).toBe("sg_singstat_search");
    expect(intent.apis).toContain("singstat");
  });

  it("rejects comparison queries that need multiple direct calls", () => {
    const plan = planQuery("Compare property prices in Orchard and Tampines");
    expect(plan.supported).toBe(false);
    if (!plan.supported) {
      expect(plan.reason).toContain("one direct tool call");
    }
  });

  it("extracts year range from query", () => {
    const intent = classifyIntent("GDP growth for the last 5 years");
    expect(intent.extractedParams["startYear"]).toBeDefined();
    expect(intent.extractedParams["endYear"]).toBeDefined();
  });

  it("routes postal code to geocode", () => {
    const intent = classifyIntent("Find 168742");
    expect(intent.intent).toBe("geospatial");
    expect(intent.tool).toBe("sg_onemap_geocode");
    expect(intent.extractedParams["postalCode"]).toBe("168742");
  });

  it("rejects chained geocode and population requests", () => {
    const plan = planQuery("Population near postal code 168742");
    expect(plan.supported).toBe(false);
    if (!plan.supported) {
      expect(plan.reason).toContain("does not chain geocoding");
    }
  });

  it("routes SORA queries to the interest-rate tool and preserves exact dates", () => {
    const intent = classifyIntent("What was SORA on 2024-01-31?");
    expect(intent.intent).toBe("financial");
    expect(intent.tool).toBe("sg_mas_interest_rates");
    expect(intent.extractedParams["date"]).toBe("2024-01-31");
  });

  it("routes master plan questions to the URA planning tool", () => {
    const intent = classifyIntent("Show the master plan zoning for Bedok");
    expect(intent.intent).toBe("property");
    expect(intent.tool).toBe("sg_ura_planning_area");
    expect(intent.extractedParams["planningArea"]).toBe("Bedok");
  });

  it("builds a single-step search query plan", () => {
    const plan = planQuery("Search for GDP datasets");
    expect(plan.supported).toBe(true);
    if (plan.supported) {
      expect(plan.step.tool).toBe("sg_singstat_search");
      expect(plan.step.input).toEqual({ keyword: "Search for GDP datasets" });
    }
  });
});
