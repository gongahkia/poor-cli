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

  it("tags property brief tools into the property profile", () => {
    const toolsets = inferToolSets("sg_property_brief");

    expect(toolsets).toEqual(expect.arrayContaining(["briefs", "property"]));
    expect(toolsets).not.toContain("diligence");
  });

  it("keeps sg_query available to both diligence and property profiles", () => {
    expect(inferToolSets("sg_query")).toEqual(expect.arrayContaining(["query", "diligence", "property"]));
  });

  it("matches profile-only filters through isToolEnabled", () => {
    const diligenceOnly = toToolsetSet(["diligence"]);
    const propertyOnly = toToolsetSet(["property"]);

    expect(isToolEnabled({ toolsets: inferToolSets("sg_business_dossier") }, diligenceOnly)).toBe(true);
    expect(isToolEnabled({ toolsets: inferToolSets("sg_business_dossier") }, propertyOnly)).toBe(false);
    expect(isToolEnabled({ toolsets: inferToolSets("sg_property_brief") }, propertyOnly)).toBe(true);
    expect(isToolEnabled({ toolsets: inferToolSets("sg_property_brief") }, diligenceOnly)).toBe(false);
  });
});
