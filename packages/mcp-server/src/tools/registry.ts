import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerPrompts } from "./prompts.js";
import { registerResources } from "./resources.js";
import { ALL_TOOL_DEFINITIONS } from "./tool-set.js";
import { registerToolDefinition } from "./tool-definition.js";
import type { ToolSet } from "./tool-definition.js";
import { isToolEnabled } from "./tool-metadata.js";

export type RegisterSurfaceOptions = {
  readonly enabledToolsets?: ReadonlySet<ToolSet>;
};

export const getRegisteredToolDefinitions = (
  options?: RegisterSurfaceOptions,
) => {
  const enabledToolsets = options?.enabledToolsets;
  if (enabledToolsets === undefined) {
    return ALL_TOOL_DEFINITIONS;
  }

  return ALL_TOOL_DEFINITIONS.filter((definition) => isToolEnabled(definition, enabledToolsets));
};

export const registerAllTools = (server: McpServer, options?: RegisterSurfaceOptions): void => {
  const definitions = getRegisteredToolDefinitions(options);
  for (const definition of definitions) {
    registerToolDefinition(server, definition);
  }
  registerResources(server, definitions);
  registerPrompts(server);
};
