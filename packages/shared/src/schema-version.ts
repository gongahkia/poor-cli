export const BRIEF_ENVELOPE_SCHEMA_VERSION = "brief-envelope/v1";
export const BUSINESS_DOSSIER_SCHEMA_VERSION = "business-dossier/v1";
export const COUNTRY_PACK_SCHEMA_VERSION = "country-pack/v1";

export const SCHEMA_VERSIONS = {
  briefEnvelope: BRIEF_ENVELOPE_SCHEMA_VERSION,
  businessDossier: BUSINESS_DOSSIER_SCHEMA_VERSION,
  countryPack: COUNTRY_PACK_SCHEMA_VERSION,
} as const;

export type SchemaSurface = keyof typeof SCHEMA_VERSIONS;
export type SchemaVersion = (typeof SCHEMA_VERSIONS)[SchemaSurface];
