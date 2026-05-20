import { describe, expect, it } from "vitest";

import { getCountryPack, getCountryPackToolDefinitions, getCountryPacks } from "../registry.js";
import { SINGAPORE_COUNTRY_PACK } from "../sg.js";
import { ALL_TOOL_DEFINITIONS } from "../../tools/tool-set.js";

describe("Singapore country pack", () => {
  it("is the stable runtime registration boundary for the existing SG surface", () => {
    expect(getCountryPacks()).toEqual([SINGAPORE_COUNTRY_PACK]);
    expect(getCountryPack("sg")).toBe(SINGAPORE_COUNTRY_PACK);
    expect(SINGAPORE_COUNTRY_PACK).toMatchObject({
      packId: "sg",
      namespace: "sg",
      status: "stable",
      country: { iso2: "SG", iso3: "SGP" },
    });
  });

  it("keeps all registered tools in the sg_* namespace", () => {
    const names = SINGAPORE_COUNTRY_PACK.toolDefinitions.map((definition) => definition.name);

    expect(names).toHaveLength(28);
    expect(names.every((name) => name.startsWith("sg_"))).toBe(true);
    expect(names).toContain("sg_cdd_report");
    expect(names).toContain("sg_resolve_counterparty");
    expect(names).toContain("sg_business_dossier");
    expect(names).toContain("sg_query");
    expect(names).toContain("sg_sanctions_screen");
    expect(names).not.toContain("sg_property_brief");
    expect(names).not.toContain("sg_macro_brief");
    expect(names).not.toContain("sg_transport_brief");
    expect(names).not.toContain("sg_datagov_search");
  });

  it("feeds the public tool-set registration without changing the hydrated surface", () => {
    const rawNames = getCountryPackToolDefinitions().map((definition) => definition.name);
    const hydratedNames = ALL_TOOL_DEFINITIONS.map((definition) => definition.name);

    expect(rawNames).toEqual(hydratedNames);
  });

  it("documents auth, resources, and governance metadata for new pack authors", () => {
    expect(SINGAPORE_COUNTRY_PACK.auth.envVars).toEqual(
      expect.arrayContaining(["OPENSANCTIONS_API_KEY", "OPENCORPORATES_API_TOKEN"]),
    );
    expect(SINGAPORE_COUNTRY_PACK.resources.map((resource) => resource.uri)).toEqual(
      expect.arrayContaining(["sg://apis", "sg://tools", "sg://runtime"]),
    );
    expect(SINGAPORE_COUNTRY_PACK.governance.schemaVersion).toBe("country-pack/v1");
    expect(SINGAPORE_COUNTRY_PACK.governance.publicDataLimits.length).toBeGreaterThan(0);
  });
});
