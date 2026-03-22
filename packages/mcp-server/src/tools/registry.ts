import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { ZodRawShape } from "zod";
import type { ToolResult } from "@sg-apis/shared";
import { wrapHandler } from "../middleware/error-handler.js";
import { registerSingStatTools } from "./singstat-tools.js";
import { registerMasTools } from "./mas-tools.js";
import { registerOneMapTools } from "./onemap-tools.js";
import { registerUraTools } from "./ura-tools.js";
import { registerDatagovTools } from "./datagov-tools.js";
import { registerHealthCheckTool } from "./health-check.js";
import { registerCacheTools } from "./cache-tools.js";
import { registerKeystoreTools } from "./keystore-tools.js";
import { registerConfigTools } from "./config-tools.js";
import { registerQueryTool } from "./query-tool.js";
import { registerResources } from "./resources.js";

export type ToolDefinition = {
  readonly name: string;
  readonly description: string;
  readonly inputSchema: ZodRawShape;
  readonly handler: (input: unknown) => Promise<ToolResult>;
};

export const registerTool = (server: McpServer, def: ToolDefinition): void => {
  server.tool(def.name, def.description, def.inputSchema, async (params) => {
    const result = await wrapHandler(def.handler)(params);
    return {
      content: result.content.map((c) => ({ type: c.type, text: c.text })),
      isError: result.isError,
    };
  });
};

export const registerAllTools = (server: McpServer): void => {
  registerSingStatTools(server);
  registerMasTools(server);
  registerOneMapTools(server);
  registerUraTools(server);
  registerDatagovTools(server);
  registerHealthCheckTool(server);
  registerCacheTools(server);
  registerKeystoreTools(server);
  registerConfigTools(server);
  registerQueryTool(server);
  registerResources(server);
};
