import type { JurisdictionConfig } from './jurisdiction';
import { SINGAPORE } from './singapore';
import { MALAYSIA } from './malaysia';

export type { JurisdictionConfig } from './jurisdiction';

const REGISTRY: Record<string, JurisdictionConfig> = {
  sg: SINGAPORE,
  my: MALAYSIA,
};

export function getJurisdiction(id: string): JurisdictionConfig | undefined {
  return REGISTRY[id];
}
export function listJurisdictions(): JurisdictionConfig[] {
  return Object.values(REGISTRY);
}
export function getDefaultJurisdiction(): JurisdictionConfig {
  return SINGAPORE;
}
