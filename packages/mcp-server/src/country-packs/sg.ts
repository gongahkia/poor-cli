import { acraToolDefinitions } from "../tools/acra-tools.js";
import { bcaToolDefinitions } from "../tools/bca-tools.js";
import { boaToolDefinitions } from "../tools/boa-tools.js";
import { briefToolDefinitions } from "../tools/brief-tools.js";
import { cacheToolDefinitions } from "../tools/cache-tools.js";
import { ceaToolDefinitions } from "../tools/cea-tools.js";
import { coeToolDefinitions } from "../tools/coe-tools.js";
import { configToolDefinitions } from "../tools/config-tools.js";
import { datagovToolDefinitions } from "../tools/datagov-tools.js";
import { ecdaToolDefinitions } from "../tools/ecda-tools.js";
import { emaToolDefinitions } from "../tools/ema-tools.js";
import { externalDiligenceToolDefinitions } from "../tools/external-diligence-tools.js";
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
import { queryToolDefinitions } from "../tools/query-tool.js";
import { sfaToolDefinitions } from "../tools/sfa-tools.js";
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
  ...singstatToolDefinitions,
  ...masToolDefinitions,
  ...onemapToolDefinitions,
  ...uraToolDefinitions,
  ...datagovToolDefinitions,
  ...paToolDefinitions,
  ...sportsgToolDefinitions,
  ...ecdaToolDefinitions,
  ...msfToolDefinitions,
  ...ltaToolDefinitions,
  ...neaToolDefinitions,
  ...hdbToolDefinitions,
  ...housingToolDefinitions,
  ...ceaToolDefinitions,
  ...bcaToolDefinitions,
  ...boaToolDefinitions,
  ...acraToolDefinitions,
  ...gebizToolDefinitions,
  ...govFeedToolDefinitions,
  ...hawkerToolDefinitions,
  ...moeToolDefinitions,
  ...mohToolDefinitions,
  ...hsaToolDefinitions,
  ...sfaToolDefinitions,
  ...nparksToolDefinitions,
  ...pubToolDefinitions,
  ...momToolDefinitions,
  ...stbToolDefinitions,
  ...coeToolDefinitions,
  ...irasToolDefinitions,
  ...spfToolDefinitions,
  ...emaToolDefinitions,
  ...visualizeToolDefinitions,
  ...nlbToolDefinitions,
  ...lawToolDefinitions,
  ...transitIntelligenceToolDefinitions,
  ...hlbToolDefinitions,
  ...externalDiligenceToolDefinitions,
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
      "SG_API_ONEMAP_EMAIL",
      "SG_API_ONEMAP_PASSWORD",
      "SG_API_URA_KEY",
      "SG_API_LTA_KEY",
    ],
    notes: "Most SG tools are no-auth. OneMap, URA, and LTA DataMall use optional runtime credentials or keystore entries.",
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
      "Credentialed sources must expose provenance, freshness, gaps, and limits rather than silently falling back to guessed values.",
    ],
    licensingNotes: [
      "ACRA, OneMap, URA, LTA, and future paid or partner sources require documented source-use review before hosted commercial workflows widen scope.",
      "Country-pack additions must keep source licensing, auth, rate-limit, caching, and attribution constraints explicit.",
    ],
    freshnessNotes: [
      "Brief-style outputs must return observed-at freshness and upstream timestamps where available.",
      "Live operational signals must remain snapshot-only unless a source-specific prediction contract is added and reviewed.",
    ],
    ownerRoles: ["core maintainer", "diligence maintainer", "country-pack maintainer", "governance maintainer"],
  },
  toolDefinitions,
});
