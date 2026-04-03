import { describe, it, expect } from "vitest";
import { classifyIntent } from "../classifier.js";

describe("classifyIntent", () => {
  // routing correctness: snapshot actual workflow names for regression safety
  it.each([
    ["Registry diligence for UEN 201912345K", "business_registry_diligence"],
    ["Architecture firm diligence for DP Architects", "architecture_firm_diligence"],
    ["Healthcare supplier diligence for ZUELLIG PHARMA", "healthcare_supplier_diligence"],
    ["Hotel operator lookup for Marina Bay Sands", "hotel_operator_lookup"],
    ["Property due diligence for Bedok HDB resale", "property_due_diligence"],
    ["Macro snapshot of Singapore", "macro_snapshot"],
    ["Transport status in Singapore right now", "transport_brief"],
    ["Environment snapshot of Singapore right now", "environment_brief"],
    ["Walk from 049178 to 048616", "route_plan"],
    ["Find a community club near 560123", "civic_discovery"],
    ["Find dataset about population", "dataset_discovery"],
  ])("routes '%s' to workflow '%s'", (query, expectedWorkflow) => {
    const result = classifyIntent(query);
    expect(result.workflow).toBe(expectedWorkflow);
    expect(result.confidence).toBeGreaterThan(0);
  });

  // param extraction
  it("extracts UEN from diligence query", () => {
    const result = classifyIntent("Registry diligence for UEN 201912345K");
    expect(result.extractedParams["uen"]).toBe("201912345K");
  });

  it("extracts postal codes for route planning", () => {
    const result = classifyIntent("Walk from 049178 to 048616");
    expect(result.extractedParams["originPostalCode"]).toBe("049178");
    expect(result.extractedParams["destinationPostalCode"]).toBe("048616");
  });

  it("extracts planning area for property query", () => {
    const result = classifyIntent("Property due diligence for Bedok");
    expect(result.extractedParams["planningArea"]).toBe("Bedok");
  });

  // confidence sanity
  it("high confidence for clear macro query", () => {
    const result = classifyIntent("Macro snapshot of Singapore");
    expect(result.confidence).toBeGreaterThanOrEqual(0.8);
  });

  it("returns a result for ambiguous queries", () => {
    const result = classifyIntent("what is the meaning of life");
    expect(result).toBeDefined();
    expect(typeof result.workflow).toBe("string");
  });
});
