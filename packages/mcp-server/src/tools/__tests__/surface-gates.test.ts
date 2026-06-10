import { afterEach, describe, expect, it } from "vitest";
import { assertFamilyEnabled, assertStreamEnabled } from "../surface-gates.js";

describe("surface rollback gates", () => {
  const originalFamilies = process.env["SG_APIS_DISABLED_FAMILIES"];
  const originalStreams = process.env["SG_APIS_DISABLED_STREAMS"];

  afterEach(() => {
    if (originalFamilies === undefined) {
      delete process.env["SG_APIS_DISABLED_FAMILIES"];
    } else {
      process.env["SG_APIS_DISABLED_FAMILIES"] = originalFamilies;
    }

    if (originalStreams === undefined) {
      delete process.env["SG_APIS_DISABLED_STREAMS"];
    } else {
      process.env["SG_APIS_DISABLED_STREAMS"] = originalStreams;
    }
  });

  it("blocks disabled families", () => {
    process.env["SG_APIS_DISABLED_FAMILIES"] = "government_rss_feeds";
    expect(() => assertFamilyEnabled("government_rss_feeds", "sg_gov_feed_catalog")).toThrowError(/disabled/i);
  });

  it("blocks disabled streams", () => {
    process.env["SG_APIS_DISABLED_STREAMS"] = "sfa_newsroom";
    expect(() => assertStreamEnabled("sfa_newsroom", "sg_gov_feed_items")).toThrowError(/disabled/i);
  });
});
