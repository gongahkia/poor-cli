import { describe, expect, it } from "vitest";

import { parseBulkInput } from "@/lib/bulk";

describe("parseBulkInput", () => {
  it("parses pasted line lists", () => {
    expect(parseBulkInput("03591300B\nDBS BANK").items).toEqual([
      { identifier: "03591300B" },
      { identifier: "DBS BANK" },
    ]);
  });

  it("parses CSV identifier columns and reports row errors", () => {
    const parsed = parseBulkInput("name,uen\nDBS,03591300B\nBroken,\nLong," + "x".repeat(129));
    expect(parsed.items).toEqual([{ identifier: "03591300B" }]);
    expect(parsed.errors).toHaveLength(2);
  });
});
