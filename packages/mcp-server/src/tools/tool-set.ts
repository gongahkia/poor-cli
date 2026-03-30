import { acraToolDefinitions } from "./acra-tools.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { bcaToolDefinitions } from "./bca-tools.js";
import { boaToolDefinitions } from "./boa-tools.js";
import { briefToolDefinitions } from "./brief-tools.js";
import { cacheToolDefinitions } from "./cache-tools.js";
import { ceaToolDefinitions } from "./cea-tools.js";
import { configToolDefinitions } from "./config-tools.js";
import { datagovToolDefinitions } from "./datagov-tools.js";
import { ecdaToolDefinitions } from "./ecda-tools.js";
import { gebizToolDefinitions } from "./gebiz-tools.js";
import { hawkerToolDefinitions } from "./hawker-tools.js";
import { healthCheckToolDefinitions } from "./health-check.js";
import { hdbToolDefinitions } from "./hdb-tools.js";
import { hlbToolDefinitions } from "./hlb-tools.js";
import { hsaToolDefinitions } from "./hsa-tools.js";
import { keystoreToolDefinitions } from "./keystore-tools.js";
import { ltaToolDefinitions } from "./lta-tools.js";
import { masToolDefinitions } from "./mas-tools.js";
import { moeToolDefinitions } from "./moe-tools.js";
import { mohToolDefinitions } from "./moh-tools.js";
import { momToolDefinitions } from "./mom-tools.js";
import { msfToolDefinitions } from "./msf-tools.js";
import { neaToolDefinitions } from "./nea-tools.js";
import { nparksToolDefinitions } from "./nparks-tools.js";
import { paToolDefinitions } from "./pa-tools.js";
import { pubToolDefinitions } from "./pub-tools.js";
import { sfaToolDefinitions } from "./sfa-tools.js";
import { sportsgToolDefinitions } from "./sportsg-tools.js";
import { stbToolDefinitions } from "./stb-tools.js";
import { onemapToolDefinitions } from "./onemap-tools.js";
import { queryToolDefinitions } from "./query-tool.js";
import { singstatToolDefinitions } from "./singstat-tools.js";
import { hydrateToolDefinition } from "./tool-metadata.js";
import { uraToolDefinitions } from "./ura-tools.js";

const RAW_TOOL_DEFINITIONS = [
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
  ...ceaToolDefinitions,
  ...bcaToolDefinitions,
  ...boaToolDefinitions,
  ...acraToolDefinitions,
  ...gebizToolDefinitions,
  ...hawkerToolDefinitions,
  ...moeToolDefinitions,
  ...mohToolDefinitions,
  ...hsaToolDefinitions,
  ...sfaToolDefinitions,
  ...nparksToolDefinitions,
  ...pubToolDefinitions,
  ...momToolDefinitions,
  ...stbToolDefinitions,
  ...hlbToolDefinitions,
  ...briefToolDefinitions,
  ...healthCheckToolDefinitions,
  ...cacheToolDefinitions,
  ...keystoreToolDefinitions,
  ...configToolDefinitions,
  ...queryToolDefinitions,
] as const satisfies readonly RegisteredToolDefinition[];

export const ALL_TOOL_DEFINITIONS: readonly RegisteredToolDefinition[] = RAW_TOOL_DEFINITIONS.map((definition) =>
  hydrateToolDefinition(definition),
);
