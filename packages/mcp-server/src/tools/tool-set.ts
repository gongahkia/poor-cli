import type { RegisteredToolDefinition } from "./tool-definition.js";
import { cacheToolDefinitions } from "./cache-tools.js";
import { configToolDefinitions } from "./config-tools.js";
import { datagovToolDefinitions } from "./datagov-tools.js";
import { healthCheckToolDefinitions } from "./health-check.js";
import { keystoreToolDefinitions } from "./keystore-tools.js";
import { masToolDefinitions } from "./mas-tools.js";
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
  ...healthCheckToolDefinitions,
  ...cacheToolDefinitions,
  ...keystoreToolDefinitions,
  ...configToolDefinitions,
  ...queryToolDefinitions,
] as const satisfies readonly RegisteredToolDefinition[];
