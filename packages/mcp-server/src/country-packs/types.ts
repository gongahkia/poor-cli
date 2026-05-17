import type { RegisteredToolDefinition } from "../tools/tool-definition.js";

export type CountryPackStatus = "proposal" | "skeleton" | "public_preview" | "stable" | "blocked";

export type CountryPackCountry = {
  readonly name: string;
  readonly iso2: string;
  readonly iso3: string;
};

export type CountryPackAuthMetadata = {
  readonly required: boolean;
  readonly envVars: readonly string[];
  readonly notes: string;
};

export type CountryPackResourceMetadata = {
  readonly uri: string;
  readonly description: string;
};

export type CountryPackGovernanceMetadata = {
  readonly schemaVersion: "country-pack/v1";
  readonly publicDataLimits: readonly string[];
  readonly licensingNotes: readonly string[];
  readonly freshnessNotes: readonly string[];
  readonly ownerRoles: readonly string[];
};

export type CountryPackRuntimeDefinition = {
  readonly packId: string;
  readonly namespace: string;
  readonly country: CountryPackCountry;
  readonly status: CountryPackStatus;
  readonly summary: string;
  readonly auth: CountryPackAuthMetadata;
  readonly resources: readonly CountryPackResourceMetadata[];
  readonly governance: CountryPackGovernanceMetadata;
  readonly toolDefinitions: readonly RegisteredToolDefinition[];
};

export const defineCountryPack = <TPack extends CountryPackRuntimeDefinition>(pack: TPack): TPack => pack;
