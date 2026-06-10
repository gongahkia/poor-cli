import { describe, expect, it } from "vitest";
import type { ToolSet } from "../tool-definition.js";
import { inferToolSets, isToolEnabled } from "../tool-metadata.js";
import { ALL_TOOL_DEFINITIONS } from "../tool-set.js";

const toToolsetSet = (values: readonly ToolSet[]): ReadonlySet<ToolSet> => new Set(values);

describe("tool metadata profile subsets", () => {
  it("tags Swee Pulse tools into the public profile", () => {
    const toolsets = inferToolSets("swee_pulse_snapshot");

    expect(toolsets).toEqual(expect.arrayContaining(["public"]));
    expect(toolsets).not.toContain("property");
  });

  it("tags Swee Shield tools into the ops profile", () => {
    const toolsets = inferToolSets("swee_shield_audit_lookup");

    expect(toolsets).toEqual(expect.arrayContaining(["ops"]));
    expect(toolsets).not.toContain("property");
    expect(inferToolSets("swee_shield_splunk_investigation_pack")).toEqual(expect.arrayContaining(["ops"]));
    expect(ALL_TOOL_DEFINITIONS.find((tool) => tool.name === "splunk_search")?.toolsets).toEqual(expect.arrayContaining(["ops"]));
  });

  it("keeps source adapters available to the public profile", () => {
    expect(inferToolSets("sg_datagov_search")).toEqual(expect.arrayContaining(["public"]));
    expect(inferToolSets("sg_datagov_search")).not.toContain("property");
  });

  it("matches profile-only filters through isToolEnabled", () => {
    const publicOnly = toToolsetSet(["public"]);
    const opsOnly = toToolsetSet(["ops"]);

    expect(isToolEnabled({ toolsets: inferToolSets("swee_pulse_snapshot") }, publicOnly)).toBe(true);
    expect(isToolEnabled({ toolsets: inferToolSets("swee_shield_audit_lookup") }, opsOnly)).toBe(true);
    expect(isToolEnabled({ toolsets: inferToolSets("sg_cache_clear") }, publicOnly)).toBe(false);
  });
});
