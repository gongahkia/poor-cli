import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { ZodRawShape } from "zod";
import type { ToolResult } from "@sg-apis/shared";
import { wrapHandler } from "../middleware/error-handler.js";

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
  // Tool modules will be imported and registered here as they are created
  void server; // placeholder
};
