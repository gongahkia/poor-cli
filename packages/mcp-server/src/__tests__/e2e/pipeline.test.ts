import { describe, it, expect } from "vitest";
import { classifyIntent } from "../../router/classifier.js";
import { planQuery } from "../../router/planner.js";

describe("E2E Pipeline", () => {
  it("routes exchange rate query to MAS", () => {
    const intent = classifyIntent("What's the SGD to USD exchange rate?");
    expect(intent.intent).toBe("financial");
    expect(intent.apis).toContain("mas");
    expect(intent.extractedParams["currency"]).toBe("SGD");
  });

  it("routes population query to OneMap", () => {
    const intent = classifyIntent("Population of Tampines");
    expect(intent.intent).toBe("demographic");
    expect(intent.apis).toContain("onemap");
    expect(intent.extractedParams["planningArea"]).toBe("Tampines");
  });

  it("routes GDP query to SingStat", () => {
    const intent = classifyIntent("Search for GDP datasets");
    expect(intent.intent).toBe("economic");
    expect(intent.apis).toContain("singstat");
  });

  it("creates comparison plan for property query", () => {
    const plan = planQuery("Compare property prices in Orchard and Tampines");
    expect(plan.steps.length).toBeGreaterThanOrEqual(1);
  });

  it("extracts year range from query", () => {
    const intent = classifyIntent("GDP growth for the last 5 years");
    expect(intent.extractedParams["startYear"]).toBeDefined();
    expect(intent.extractedParams["endYear"]).toBeDefined();
  });

  it("routes postal code to geocode", () => {
    const intent = classifyIntent("Find 168742");
    expect(intent.intent).toBe("geospatial");
    expect(intent.extractedParams["postalCode"]).toBe("168742");
  });

  it("creates sequential plan for geocode+population", () => {
    const plan = planQuery("Population near postal code 168742");
    expect(plan.parallel).toBe(false);
    expect(plan.steps.length).toBe(2);
    expect(plan.steps[1]?.dependsOn).toBe(0);
  });
});
