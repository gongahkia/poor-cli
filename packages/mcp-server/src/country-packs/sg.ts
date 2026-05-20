import { acraToolDefinitions } from "../tools/acra-tools.js";
import { bcaToolDefinitions } from "../tools/bca-tools.js";
import { boaToolDefinitions } from "../tools/boa-tools.js";
import { briefToolDefinitions } from "../tools/brief-tools.js";
import { cacheToolDefinitions } from "../tools/cache-tools.js";
import { cddToolDefinitions } from "../tools/cdd-tools.js";
import { ceaToolDefinitions } from "../tools/cea-tools.js";
import { configToolDefinitions } from "../tools/config-tools.js";
import { externalDiligenceToolDefinitions } from "../tools/external-diligence-tools.js";
import { gebizToolDefinitions } from "../tools/gebiz-tools.js";
import { healthCheckToolDefinitions } from "../tools/health-check.js";
import { hlbToolDefinitions } from "../tools/hlb-tools.js";
import { hsaToolDefinitions } from "../tools/hsa-tools.js";
import { keystoreToolDefinitions } from "../tools/keystore-tools.js";
import { queryToolDefinitions } from "../tools/query-tool.js";
import { traceToolDefinitions } from "../tools/trace-tools.js";
import { defineCountryPack } from "./types.js";

const toolDefinitions = [
  ...ceaToolDefinitions,
  ...bcaToolDefinitions,
  ...boaToolDefinitions,
  ...acraToolDefinitions,
  ...gebizToolDefinitions,
  ...hsaToolDefinitions,
  ...hlbToolDefinitions,
  ...externalDiligenceToolDefinitions,
  ...cddToolDefinitions,
  ...briefToolDefinitions,
  ...healthCheckToolDefinitions,
  ...cacheToolDefinitions,
  ...keystoreToolDefinitions,
  ...configToolDefinitions,
  ...traceToolDefinitions,
  ...queryToolDefinitions,
] as const;

export const SINGAPORE_COUNTRY_PACK = defineCountryPack({
  packId: "sg",
  namespace: "sg",
  country: {
    name: "Singapore",
    iso2: "SG",
    iso3: "SGP",
  },
  status: "stable",
  summary: "Stable Singapore public-data and due-diligence runtime preserving the existing sg_* contract namespace.",
  auth: {
    required: false,
    envVars: [
      "OPENSANCTIONS_API_KEY",
      "OPENCORPORATES_API_TOKEN",
    ],
    notes: "Core CDD registry tools are no-auth. External diligence adapters require source-specific commercial-use review and credentials.",
  },
  resources: [
    { uri: "sg://apis", description: "Singapore API family catalog." },
    { uri: "sg://tools", description: "Singapore tool catalog." },
    { uri: "sg://runtime", description: "Singapore runtime dependency and auth surface." },
    { uri: "sg://recipes", description: "Singapore workflow recipes." },
    { uri: "sg://playbooks", description: "Singapore persona playbooks." },
    { uri: "sg://benchmarks", description: "Singapore workflow benchmark catalog." },
  ],
  governance: {
    schemaVersion: "country-pack/v1",
    publicDataLimits: [
      "No private ownership, shareholder, director, sanctions, AML, credit, legal, tax, or investment opinion is inferred from public data gaps.",
      "Credentialed external diligence sources must expose provenance, freshness, gaps, and limits rather than silently falling back to guessed values.",
    ],
    licensingNotes: [
      "ACRA-derived commercial diligence outputs and external diligence adapters require documented source-use review before hosted commercial workflows widen scope.",
      "CDD additions must keep source licensing, auth, rate-limit, caching, and attribution constraints explicit.",
    ],
    freshnessNotes: [
      "Brief-style outputs must return observed-at freshness and upstream timestamps where available.",
      "CDD reports must preserve source freshness, unresolved gaps, and limits in exported artifacts.",
    ],
    ownerRoles: ["core maintainer", "diligence maintainer", "country-pack maintainer", "governance maintainer"],
  },
  toolDefinitions,
});
