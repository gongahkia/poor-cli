import { describe, expect, it } from "vitest";

import { rankSearchSuggestions } from "@/lib/search/rank-search-suggestions";

describe("rankSearchSuggestions", () => {
  it("prefers label and alias matches", () => {
    const results = rankSearchSuggestions("dbs", [
      { id: "1", label: "OCBC BANK", aliases: ["03591300B"] },
      { id: "2", label: "DBS BANK LTD", aliases: ["196800306E"] },
    ]);

    expect(results[0]?.id).toBe("2");
  });

  it("returns the first limited rows for blank queries", () => {
    expect(rankSearchSuggestions("", [
      { id: "1", label: "A" },
      { id: "2", label: "B" },
    ], 1)).toEqual([{ id: "1", label: "A" }]);
  });
});
