import { acraToolDefinitions } from "./acra-tools.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { bcaToolDefinitions } from "./bca-tools.js";
import { briefToolDefinitions } from "./brief-tools.js";
import { cacheToolDefinitions } from "./cache-tools.js";
import { ceaToolDefinitions } from "./cea-tools.js";
import { configToolDefinitions } from "./config-tools.js";
import { datagovToolDefinitions } from "./datagov-tools.js";
import { healthCheckToolDefinitions } from "./health-check.js";
import { hdbToolDefinitions } from "./hdb-tools.js";
import { keystoreToolDefinitions } from "./keystore-tools.js";
import { ltaToolDefinitions } from "./lta-tools.js";
import { masToolDefinitions } from "./mas-tools.js";
import { neaToolDefinitions } from "./nea-tools.js";
import { onemapToolDefinitions } from "./onemap-tools.js";
import { queryToolDefinitions } from "./query-tool.js";
import { singstatToolDefinitions } from "./singstat-tools.js";
import { uraToolDefinitions } from "./ura-tools.js";

export const ALL_TOOL_DEFINITIONS = [
  ...singstatToolDefinitions,
  ...masToolDefinitions,
  ...onemapToolDefinitions,
  ...uraToolDefinitions,
  ...datagovToolDefinitions,
  ...ltaToolDefinitions,
  ...neaToolDefinitions,
  ...hdbToolDefinitions,
  ...ceaToolDefinitions,
  ...bcaToolDefinitions,
  ...acraToolDefinitions,
  ...briefToolDefinitions,
  ...healthCheckToolDefinitions,
  ...cacheToolDefinitions,
  ...keystoreToolDefinitions,
  ...configToolDefinitions,
  ...queryToolDefinitions,
] as const satisfies readonly RegisteredToolDefinition[];
