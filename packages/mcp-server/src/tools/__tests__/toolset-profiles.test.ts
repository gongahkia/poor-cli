import { describe, expect, it } from "vitest";
import { ALL_TOOLSETS, TOOLSET_PROFILE_PRESETS, resolveEnabledToolsets } from "../toolset-profiles.js";

describe("toolset profile resolution", () => {
  it("uses all toolsets by default in stdio mode", () => {
    const resolved = resolveEnabledToolsets({ transportMode: "stdio" });
    expect(new Set(ALL_TOOLSETS)).toEqual(resolved);
  });

  it("uses public profile defaults in http mode", () => {
    const resolved = resolveEnabledToolsets({ transportMode: "http" });
    expect(new Set(TOOLSET_PROFILE_PRESETS.public)).toEqual(resolved);
  });

  it("resolves predefined diligence profile", () => {
    const resolved = resolveEnabledToolsets({
      transportMode: "http",
      configuredProfile: "diligence",
    });
    expect(new Set(TOOLSET_PROFILE_PRESETS.diligence)).toEqual(resolved);
  });

  it("resolves predefined CDD report profile", () => {
    const resolved = resolveEnabledToolsets({
      transportMode: "http",
      configuredProfile: "cdd_report",
    });
    expect(new Set(TOOLSET_PROFILE_PRESETS.cdd_report)).toEqual(resolved);
    expect(resolved.has("property")).toBe(false);
  });

  it("prioritizes explicit SG_APIS_TOOLSETS over profile presets", () => {
    const resolved = resolveEnabledToolsets({
      transportMode: "http",
      configuredToolsets: "public,query,ops",
      configuredProfile: "diligence",
    });
    expect(resolved).toEqual(new Set(["public", "query", "ops"]));
  });

  it("rejects unsupported profile names", () => {
    expect(() =>
      resolveEnabledToolsets({
        transportMode: "http",
        configuredProfile: "finance",
      }),
    ).toThrow("Unsupported tool profile");
  });
});
