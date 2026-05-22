import { acraToolDefinitions } from "../tools/acra-tools.js";
import { bcaToolDefinitions } from "../tools/bca-tools.js";
import { boaToolDefinitions } from "../tools/boa-tools.js";
import { cacheToolDefinitions } from "../tools/cache-tools.js";
import { ceaToolDefinitions } from "../tools/cea-tools.js";
import { coeToolDefinitions } from "../tools/coe-tools.js";
import { configToolDefinitions } from "../tools/config-tools.js";
import { datagovToolDefinitions } from "../tools/datagov-tools.js";
import { ecdaToolDefinitions } from "../tools/ecda-tools.js";
import { emaToolDefinitions } from "../tools/ema-tools.js";
import { gebizToolDefinitions } from "../tools/gebiz-tools.js";
import { govFeedToolDefinitions } from "../tools/govfeeds-tools.js";
import { hawkerToolDefinitions } from "../tools/hawker-tools.js";
import { hdbToolDefinitions } from "../tools/hdb-tools.js";
import { healthCheckToolDefinitions } from "../tools/health-check.js";
import { hlbToolDefinitions } from "../tools/hlb-tools.js";
import { housingToolDefinitions } from "../tools/housing-tools.js";
import { hsaToolDefinitions } from "../tools/hsa-tools.js";
import { irasToolDefinitions } from "../tools/iras-tools.js";
import { keystoreToolDefinitions } from "../tools/keystore-tools.js";
import { lawToolDefinitions } from "../tools/law-tools.js";
import { ltaToolDefinitions } from "../tools/lta-tools.js";
import { masToolDefinitions } from "../tools/mas-tools.js";
import { moeToolDefinitions } from "../tools/moe-tools.js";
import { mohToolDefinitions } from "../tools/moh-tools.js";
import { momToolDefinitions } from "../tools/mom-tools.js";
import { msfToolDefinitions } from "../tools/msf-tools.js";
import { neaToolDefinitions } from "../tools/nea-tools.js";
import { nlbToolDefinitions } from "../tools/nlb-tools.js";
import { nparksToolDefinitions } from "../tools/nparks-tools.js";
import { onemapToolDefinitions } from "../tools/onemap-tools.js";
import { paToolDefinitions } from "../tools/pa-tools.js";
import { pubToolDefinitions } from "../tools/pub-tools.js";
import { pulseToolDefinitions } from "../tools/pulse-tools.js";
import { sfaToolDefinitions } from "../tools/sfa-tools.js";
import { shieldToolDefinitions } from "../tools/shield-tools.js";
import { singstatToolDefinitions } from "../tools/singstat-tools.js";
import { spfToolDefinitions } from "../tools/spf-tools.js";
import { sportsgToolDefinitions } from "../tools/sportsg-tools.js";
import { stbToolDefinitions } from "../tools/stb-tools.js";
import { traceToolDefinitions } from "../tools/trace-tools.js";
import { transitIntelligenceToolDefinitions } from "../tools/transit-intelligence-tools.js";
import { uraToolDefinitions } from "../tools/ura-tools.js";
import { visualizeToolDefinitions } from "../tools/visualize-tools.js";
import { defineCountryPack } from "./types.js";

const toolDefinitions = [
  ...shieldToolDefinitions,
  ...pulseToolDefinitions,
  ...datagovToolDefinitions,
  ...singstatToolDefinitions,
  ...masToolDefinitions,
  ...onemapToolDefinitions,
  ...ltaToolDefinitions,
  ...neaToolDefinitions,
  ...uraToolDefinitions,
  ...hdbToolDefinitions,
  ...housingToolDefinitions,
  ...transitIntelligenceToolDefinitions,
  ...visualizeToolDefinitions,
  ...govFeedToolDefinitions,
  ...acraToolDefinitions,
  ...bcaToolDefinitions,
  ...boaToolDefinitions,
  ...ceaToolDefinitions,
  ...gebizToolDefinitions,
  ...hsaToolDefinitions,
  ...hlbToolDefinitions,
  ...hawkerToolDefinitions,
  ...moeToolDefinitions,
  ...mohToolDefinitions,
  ...sfaToolDefinitions,
  ...nparksToolDefinitions,
  ...nlbToolDefinitions,
  ...paToolDefinitions,
  ...sportsgToolDefinitions,
  ...ecdaToolDefinitions,
  ...msfToolDefinitions,
  ...pubToolDefinitions,
  ...momToolDefinitions,
  ...stbToolDefinitions,
  ...coeToolDefinitions,
  ...irasToolDefinitions,
  ...spfToolDefinitions,
  ...emaToolDefinitions,
  ...lawToolDefinitions,
  ...healthCheckToolDefinitions,
  ...cacheToolDefinitions,
  ...keystoreToolDefinitions,
  ...configToolDefinitions,
  ...traceToolDefinitions,
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
  summary: "Swee SG public-data runtime with Shield policy/audit tools and Pulse city signals.",
  auth: {
    required: false,
    envVars: [
      "OPENSANCTIONS_API_KEY",
      "OPENCORPORATES_API_TOKEN",
    ],
    notes: "Core Shield and Pulse tools are no-auth. Source adapters retain their upstream credential requirements.",
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
      "Public-data gaps are surfaced as coverage limits, not inferred facts.",
      "Credentialed sources must expose provenance, freshness, gaps, and limits rather than silently falling back to guessed values.",
    ],
    licensingNotes: [
      "Hosted use must keep source licensing, auth, rate-limit, caching, and attribution constraints explicit.",
      "Swee Pulse outputs are operational signals, not official advisories or emergency instructions.",
    ],
    freshnessNotes: [
      "Brief-style outputs must return observed-at freshness and upstream timestamps where available.",
      "Pulse snapshots must preserve source freshness, unresolved gaps, and limits.",
    ],
    ownerRoles: ["core maintainer", "diligence maintainer", "country-pack maintainer", "governance maintainer"],
  },
  toolDefinitions,
});
