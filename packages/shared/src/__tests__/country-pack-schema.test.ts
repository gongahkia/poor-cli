import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { CountryPackEnvelopeSchema } from "../schemas/index.js";

const root = resolve(import.meta.dirname, "../../../..");

describe("country-pack envelope schema", () => {
  it("accepts the country-pack template fixture", () => {
    const fixture = JSON.parse(readFileSync(resolve(root, "examples/country-pack-template.json"), "utf8"));

    expect(CountryPackEnvelopeSchema.safeParse(fixture).success).toBe(true);
  });

  it("requires licensing, freshness, and public-data-limit metadata", () => {
    const result = CountryPackEnvelopeSchema.safeParse({
      schemaVersion: "country-pack/v1",
      packId: "my",
      country: { name: "Malaysia", iso2: "MY", iso3: "MYS" },
      status: "proposal",
      summary: "Incomplete pack",
      tools: [],
      examples: [],
      contributionNotes: [],
    });

    expect(result.success).toBe(false);
  });
});
