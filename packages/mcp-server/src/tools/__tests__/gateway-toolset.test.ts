import { describe, it, expect } from "vitest";
import { ALL_TOOL_DEFINITIONS } from "../tool-set.js";
import { isToolEnabled } from "../tool-metadata.js";
import type { ToolSet } from "../tool-definition.js";

describe("REST gateway toolset filtering", () => {
  const publicToolsets: ReadonlySet<ToolSet> = new Set(["public", "briefs", "query", "health"]);

  it("excludes ops tools from default public toolsets", () => {
    const opsTools = ALL_TOOL_DEFINITIONS.filter(
      (t) => t.name.startsWith("sg_cache_") || t.name.startsWith("sg_key_") || t.name.startsWith("sg_config_"),
    );
    expect(opsTools.length).toBeGreaterThan(0);
    for (const tool of opsTools) {
      expect(isToolEnabled(tool, publicToolsets)).toBe(false);
    }
  });

  it("includes retained CDD registry tools in default toolsets", () => {
    const publicTools = ALL_TOOL_DEFINITIONS.filter((t) => t.name === "sg_acra_entities");
    expect(publicTools.length).toBe(1);
    expect(isToolEnabled(publicTools[0]!, publicToolsets)).toBe(true);
  });

  it("includes brief tools in default toolsets", () => {
    const briefTools = ALL_TOOL_DEFINITIONS.filter((t) => t.name === "sg_business_dossier");
    expect(briefTools.length).toBe(1);
    expect(isToolEnabled(briefTools[0]!, publicToolsets)).toBe(true);
  });

  it("includes ops tools only when ops toolset is enabled", () => {
    const withOps: ReadonlySet<ToolSet> = new Set(["public", "briefs", "query", "health", "ops"]);
    const cacheTools = ALL_TOOL_DEFINITIONS.filter((t) => t.name === "sg_cache_stats");
    expect(cacheTools.length).toBe(1);
    expect(isToolEnabled(cacheTools[0]!, withOps)).toBe(true);
  });

  it("filtered count is less than total when ops excluded", () => {
    const enabled = ALL_TOOL_DEFINITIONS.filter((t) => isToolEnabled(t, publicToolsets));
    expect(enabled.length).toBeLessThan(ALL_TOOL_DEFINITIONS.length);
    expect(enabled.length).toBeGreaterThan(0);
  });
});
