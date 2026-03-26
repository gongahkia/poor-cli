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

  it("routes GDP dataset discovery queries to the dataset workflow", () => {
    const intent = classifyIntent("Search for GDP datasets");
    expect(intent.intent).toBe("dataset");
    expect(intent.workflow).toBe("dataset_discovery");
    expect(intent.apis).toContain("datagov");
  });

  it("rejects comparison queries that need multiple direct calls", () => {
    const plan = planQuery("Compare property prices in Orchard and Tampines");
    expect(plan.supported).toBe(false);
    if (!plan.supported) {
      expect(plan.reason).toContain("comparison workflows");
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

  it("builds a demographic workflow from a postal code", () => {
    const plan = planQuery("Demographic profile for postal code 168742");
    expect(plan.supported).toBe(true);
    if (plan.supported) {
      expect(plan.workflow).toBe("demographic_profile");
      expect(plan.steps.map((step) => step.tool)).toEqual([
        "sg_onemap_geocode",
        "sg_ura_planning_area",
        "sg_onemap_population",
        "sg_onemap_population",
      ]);
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

  it("builds a dataset discovery query plan", () => {
    const plan = planQuery("Search for GDP datasets");
    expect(plan.supported).toBe(true);
    if (plan.supported) {
      expect(plan.workflow).toBe("dataset_discovery");
      expect(plan.steps).toHaveLength(2);
      expect(plan.steps[0]!.tool).toBe("sg_datagov_search");
      expect(plan.steps[1]!.tool).toBe("sg_datagov_get");
    }
  });

  it("routes live bus arrival queries to LTA", () => {
    const intent = classifyIntent("Bus arrivals for stop 83139 service 851");
    expect(intent.intent).toBe("transport");
    expect(intent.tool).toBe("sg_lta_bus_arrivals");
    expect(intent.extractedParams["busStopCode"]).toBe("83139");
  });

  it("routes forecast queries to NEA", () => {
    const intent = classifyIntent("2 hour forecast for Tampines");
    expect(intent.intent).toBe("environment");
    expect(intent.tool).toBe("sg_nea_forecast_2hr");
    expect(intent.extractedParams["planningArea"]).toBe("Tampines");
  });

  it("routes broad transport snapshot queries to the transport brief workflow", () => {
    const intent = classifyIntent("Transport status in Singapore right now");
    expect(intent.intent).toBe("transport");
    expect(intent.workflow).toBe("transport_brief");
  });

  it("routes broad environment snapshot queries to the environment brief workflow", () => {
    const intent = classifyIntent("Environment snapshot of Singapore right now");
    expect(intent.intent).toBe("environment");
    expect(intent.workflow).toBe("environment_brief");
  });

  it("routes HDB resale queries to the curated HDB tool", () => {
    const intent = classifyIntent("HDB resale prices in Bedok from 2026-01 to 2026-03");
    expect(intent.intent).toBe("housing");
    expect(intent.tool).toBe("sg_hdb_resale_prices");
    expect(intent.extractedParams["planningArea"]).toBe("Bedok");
    expect(intent.extractedParams["startMonth"]).toBe("2026-01");
    expect(intent.extractedParams["endMonth"]).toBe("2026-03");
  });
});
