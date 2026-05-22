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

  it("includes retained source-adapter tools in default toolsets", () => {
    const publicTools = ALL_TOOL_DEFINITIONS.filter((t) => t.name === "sg_datagov_search");
    expect(publicTools.length).toBe(1);
    expect(isToolEnabled(publicTools[0]!, publicToolsets)).toBe(true);
  });

  it("includes Pulse tools in default toolsets", () => {
    const followUpTools = [
      "swee_pulse_snapshot",
      "swee_pulse_weather",
      "swee_pulse_mobility",
      "swee_pulse_explain",
    ];

    for (const toolName of followUpTools) {
      const tool = ALL_TOOL_DEFINITIONS.find((definition) => definition.name === toolName);
      expect(tool, `${toolName} definition should exist`).toBeDefined();
      expect(isToolEnabled(tool!, publicToolsets), `${toolName} should be enabled for web dashboard calls`).toBe(true);
    }
  });

  it("excludes Shield tools from default public toolsets", () => {
    const shieldTools = ALL_TOOL_DEFINITIONS.filter((t) => t.name === "swee_shield_audit_lookup");
    expect(shieldTools.length).toBe(1);
    expect(isToolEnabled(shieldTools[0]!, publicToolsets)).toBe(false);
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
