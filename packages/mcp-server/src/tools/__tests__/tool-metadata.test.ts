import { describe, expect, it } from "vitest";
import type { ToolSet } from "../tool-definition.js";
import { inferToolSets, isToolEnabled } from "../tool-metadata.js";

const toToolsetSet = (values: readonly ToolSet[]): ReadonlySet<ToolSet> => new Set(values);

describe("tool metadata profile subsets", () => {
  it("tags business dossier tools into the diligence profile", () => {
    const toolsets = inferToolSets("sg_business_dossier");

    expect(toolsets).toEqual(expect.arrayContaining(["briefs", "diligence"]));
    expect(toolsets).not.toContain("property");
  });

  it("tags external diligence tools into the diligence profile", () => {
    const toolsets = inferToolSets("sg_sanctions_screen");

    expect(toolsets).toEqual(expect.arrayContaining(["public", "diligence"]));
    expect(toolsets).not.toContain("property");
  });

  it("keeps sg_query available to the diligence profile", () => {
    expect(inferToolSets("sg_query")).toEqual(expect.arrayContaining(["query", "diligence"]));
    expect(inferToolSets("sg_query")).not.toContain("property");
  });

  it("matches profile-only filters through isToolEnabled", () => {
    const diligenceOnly = toToolsetSet(["diligence"]);

    expect(isToolEnabled({ toolsets: inferToolSets("sg_business_dossier") }, diligenceOnly)).toBe(true);
    expect(isToolEnabled({ toolsets: inferToolSets("sg_sanctions_screen") }, diligenceOnly)).toBe(true);
    expect(isToolEnabled({ toolsets: inferToolSets("sg_property_brief") }, diligenceOnly)).toBe(false);
  });
});
