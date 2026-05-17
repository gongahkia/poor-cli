import { SINGAPORE_COUNTRY_PACK } from "./sg.js";
import type { CountryPackRuntimeDefinition } from "./types.js";

export const COUNTRY_PACKS = [SINGAPORE_COUNTRY_PACK] as const satisfies readonly CountryPackRuntimeDefinition[];

export const getCountryPacks = (): readonly CountryPackRuntimeDefinition[] => COUNTRY_PACKS;

export const getCountryPack = (packId: string): CountryPackRuntimeDefinition | undefined =>
  COUNTRY_PACKS.find((pack) => pack.packId === packId);

export const getCountryPackToolDefinitions = () =>
  COUNTRY_PACKS.flatMap((pack) => [...pack.toolDefinitions]);
