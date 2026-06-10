import { describe, expect, it } from "vitest";
import {
  normalizeBusinessNameForMatch,
  scoreBusinessNameMatch,
} from "../name-matching.js";

describe("business name matching", () => {
  it("normalizes case, punctuation, ampersands, and legal suffixes", () => {
    expect(normalizeBusinessNameForMatch("DBS Bank Pte. Ltd.")).toBe("dbs bank");
    expect(scoreBusinessNameMatch("Foo & Bar", "FOO AND BAR PTE LTD")).toMatchObject({
      matches: true,
      method: "legal_suffix_normalized",
    });
  });

  it("treats short aliases such as dbs as bounded name matches", () => {
    expect(scoreBusinessNameMatch("dbs", "DBS Bank Ltd")).toMatchObject({
      matches: true,
      method: "alias_token",
      score: 0.92,
    });
  });

  it("supports bounded typo matching without matching unrelated names", () => {
    expect(scoreBusinessNameMatch("Datacorp", "Datacrop")).toMatchObject({
      matches: true,
      method: "typo",
    });
    expect(scoreBusinessNameMatch("DBS", "OCBC Bank")).toMatchObject({
      matches: false,
    });
  });
});
