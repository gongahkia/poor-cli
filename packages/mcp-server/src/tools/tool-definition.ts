import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { ZodRawShape } from "zod";
import type { ToolResult } from "@sg-apis/shared";
import { wrapHandler } from "../middleware/error-handler.js";

export type ToolSurface = "canonical" | "operational" | "experimental";

export type ToolCatalogEntry = {
  readonly name: string;
  readonly description: string;
  readonly surface: ToolSurface;
  readonly preferred?: boolean;
  readonly positioning?: string;
  readonly scopeNotes?: readonly string[];
};

export type RegisteredToolDefinition = ToolCatalogEntry & {
  readonly inputSchema: ZodRawShape;
  readonly handler: (input: unknown) => Promise<ToolResult>;
};

export const toToolCatalogEntry = (definition: RegisteredToolDefinition): ToolCatalogEntry => {
  const { name, description, surface, preferred, positioning, scopeNotes } = definition;
  return {
    name,
    description,
    surface,
    ...(preferred === undefined ? {} : { preferred }),
    ...(positioning === undefined ? {} : { positioning }),
    ...(scopeNotes === undefined ? {} : { scopeNotes }),
  };
};

export const registerToolDefinition = (server: McpServer, definition: RegisteredToolDefinition): void => {
  server.tool(definition.name, definition.description, definition.inputSchema, async (params) => {
    const result = await wrapHandler(definition.name, definition.handler)(params);
    return {
      content: result.content.map((content) => ({ type: content.type, text: content.text })),
      isError: result.isError,
      ...(result.structuredContent === undefined ? {} : { structuredContent: result.structuredContent }),
    };
  });
};
