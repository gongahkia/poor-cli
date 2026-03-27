import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { QueryOutcomeSchema } from "../index.js";

const readGolden = (name: string) => {
  const url = new URL(`../../../../examples/golden-outputs/${name}`, import.meta.url);
  return JSON.parse(readFileSync(url, "utf8"));
};

describe("query golden outputs", () => {
  it("keeps the completed query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-completed.json"));

    expect(payload.status).toBe("completed");
  });

  it("keeps the blocked query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-blocked.json"));

    expect(payload.status).toBe("blocked");
  });

  it("keeps the unsupported query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-unsupported.json"));

    expect(payload.status).toBe("unsupported");
  });

  it("keeps the failed query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-failed.json"));

    expect(payload.status).toBe("failed");
  });
});
