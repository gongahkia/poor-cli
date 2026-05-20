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

  it("allows browser-local 200-row batches", () => {
    const parsed = parseBulkInput(Array.from({ length: 200 }, (_, index) => `COMPANY ${index}`).join("\n"));
    expect(parsed.items).toHaveLength(200);
    expect(parsed.errors).toHaveLength(0);

    expect(parseBulkInput(Array.from({ length: 201 }, (_, index) => `COMPANY ${index}`).join("\n")).errors)
      .toEqual(expect.arrayContaining([
        expect.objectContaining({ message: "Only the first 200 rows can be checked in one batch." }),
      ]));
  });
});
