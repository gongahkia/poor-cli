import { describe, expect, it } from "vitest";
import { DatagovGetSchema } from "../schemas/index.js";

describe("data.gov.sg get schema contract", () => {
  it("accepts dataset metadata lookup inputs", () => {
    expect(
      DatagovGetSchema.safeParse({
        datasetId: "population-by-subzone",
        format: "json",
      }).success,
    ).toBe(true);
  });

  it("rejects row-level pagination and filter fields", () => {
    expect(
      DatagovGetSchema.safeParse({
        datasetId: "population-by-subzone",
        limit: 10,
        offset: 5,
        filters: { year: "2024" },
      }).success,
    ).toBe(false);
  });
});
