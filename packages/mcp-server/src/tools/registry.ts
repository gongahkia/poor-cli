import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerResources } from "./resources.js";
import { ALL_TOOL_DEFINITIONS } from "./tool-set.js";
import { registerToolDefinition } from "./tool-definition.js";

export const registerAllTools = (server: McpServer): void => {
  for (const definition of ALL_TOOL_DEFINITIONS) {
    registerToolDefinition(server, definition);
  }
  registerResources(server);
};
