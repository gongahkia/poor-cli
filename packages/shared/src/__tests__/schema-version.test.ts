import { describe, expect, it } from "vitest";

import {
  BRIEF_ENVELOPE_SCHEMA_VERSION,
  BUSINESS_DOSSIER_SCHEMA_VERSION,
  COUNTRY_PACK_SCHEMA_VERSION,
  SCHEMA_VERSIONS,
} from "../schema-version.js";

describe("schema version contracts", () => {
  it("pins the public schema surfaces to explicit contract ids", () => {
    expect(BRIEF_ENVELOPE_SCHEMA_VERSION).toBe("brief-envelope/v1");
    expect(BUSINESS_DOSSIER_SCHEMA_VERSION).toBe("business-dossier/v1");
    expect(COUNTRY_PACK_SCHEMA_VERSION).toBe("country-pack/v1");
  });

  it("exports all public schema versions from one registry", () => {
    expect(SCHEMA_VERSIONS).toEqual({
      briefEnvelope: "brief-envelope/v1",
      businessDossier: "business-dossier/v1",
      countryPack: "country-pack/v1",
    });
  });
});
