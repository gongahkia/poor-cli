import { describe, expect, it } from "vitest";
import { extractCivicModules } from "../extractors.js";

describe("extractCivicModules", () => {
  it("detects ecda from childcare keyword", () => {
    expect(extractCivicModules("Find childcare near 560123")).toEqual(["ecda"]);
  });

  it("detects msf from family service centre", () => {
    expect(extractCivicModules("Find a family service centre near 460123")).toEqual(["msf"]);
  });

  it("detects sportsg from swimming pool", () => {
    expect(extractCivicModules("Find a swimming pool in Bedok")).toEqual(["sportsg"]);
  });

  it("detects pa from community club", () => {
    expect(extractCivicModules("Community club near 560230")).toEqual(["pa"]);
  });

  it("detects multiple modules in one query", () => {
    const modules = extractCivicModules("Compare childcare and family services in Bedok vs Clementi");
    expect(new Set(modules)).toEqual(new Set(["ecda", "msf"]));
  });

  it("returns empty for non-civic queries", () => {
    expect(extractCivicModules("Macro snapshot of Singapore")).toEqual([]);
  });
});
