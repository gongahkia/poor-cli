import type { RegisteredToolDefinition } from "./tool-definition.js";
import { hydrateToolDefinition } from "./tool-metadata.js";
import { getCountryPackToolDefinitions } from "../country-packs/registry.js";

const RAW_TOOL_DEFINITIONS = getCountryPackToolDefinitions() satisfies readonly RegisteredToolDefinition[];

export const ALL_TOOL_DEFINITIONS: readonly RegisteredToolDefinition[] = RAW_TOOL_DEFINITIONS.map((definition) =>
  hydrateToolDefinition(definition),
);
