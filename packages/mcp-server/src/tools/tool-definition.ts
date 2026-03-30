import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { ToolAnnotations } from "@modelcontextprotocol/sdk/types.js";
import type { ZodRawShape, ZodTypeAny } from "zod";
import { registerAppTool } from "@modelcontextprotocol/ext-apps/server";
import type { ToolResult } from "@sg-apis/shared";
import { wrapHandler } from "../middleware/error-handler.js";

export type ToolSurface = "canonical" | "operational" | "experimental";
export type ToolSet = "public" | "briefs" | "query" | "health" | "ops" | "diligence" | "property";

export type ToolCatalogEntry = {
  readonly name: string;
  readonly title?: string;
  readonly description: string;
  readonly surface: ToolSurface;
  readonly preferred?: boolean;
  readonly positioning?: string;
  readonly scopeNotes?: readonly string[];
  readonly annotations?: ToolAnnotations;
  readonly toolsets?: readonly ToolSet[];
  readonly hasOutputSchema?: boolean;
};

export type RegisteredToolDefinition = ToolCatalogEntry & {
  readonly inputSchema: ZodRawShape;
  readonly outputSchema?: ZodTypeAny;
  readonly _meta?: Readonly<Record<string, unknown>>;
  readonly handler: (input: unknown) => Promise<ToolResult>;
};

export const toToolCatalogEntry = (definition: RegisteredToolDefinition): ToolCatalogEntry => {
  const {
    name,
    title,
    description,
    surface,
    preferred,
    positioning,
    scopeNotes,
    annotations,
    toolsets,
    outputSchema,
  } = definition;
  return {
    name,
    ...(title === undefined ? {} : { title }),
    description,
    surface,
    ...(preferred === undefined ? {} : { preferred }),
    ...(positioning === undefined ? {} : { positioning }),
    ...(scopeNotes === undefined ? {} : { scopeNotes }),
    ...(annotations === undefined ? {} : { annotations }),
    ...(toolsets === undefined ? {} : { toolsets }),
    ...(outputSchema === undefined ? {} : { hasOutputSchema: true }),
  };
};

export const registerToolDefinition = (server: McpServer, definition: RegisteredToolDefinition): void => {
  const config = {
    ...(definition.title === undefined ? {} : { title: definition.title }),
    description: definition.description,
    inputSchema: definition.inputSchema,
    ...(definition.outputSchema === undefined ? {} : { outputSchema: definition.outputSchema }),
    ...(definition.annotations === undefined ? {} : { annotations: definition.annotations }),
    ...(definition._meta === undefined ? {} : { _meta: definition._meta }),
  };

  const handler = async (params: unknown) => {
    const result = await wrapHandler(definition.name, definition.handler)(params);
    return {
      content: result.content.map((content) => (
        content.type === "text"
          ? { type: content.type, text: content.text }
          : {
              type: content.type,
              uri: content.uri,
              name: content.name,
              ...(content.title === undefined ? {} : { title: content.title }),
              ...(content.description === undefined ? {} : { description: content.description }),
              ...(content.mimeType === undefined ? {} : { mimeType: content.mimeType }),
              ...(content.annotations === undefined ? {} : { annotations: content.annotations }),
              ...(content.icons === undefined ? {} : { icons: content.icons }),
              ...(content._meta === undefined ? {} : { _meta: content._meta }),
            }
      )),
      isError: result.isError,
      ...(result.structuredContent === undefined ? {} : { structuredContent: result.structuredContent }),
      ...(result._meta === undefined ? {} : { _meta: result._meta }),
    } as CallToolResult;
  };

  const hasUiMeta = definition._meta !== undefined
    && typeof definition._meta === "object"
    && definition._meta !== null
    && (
      (typeof definition._meta["ui/resourceUri"] === "string" && definition._meta["ui/resourceUri"] !== "")
      || (
        typeof definition._meta["ui"] === "object"
        && definition._meta["ui"] !== null
        && typeof (definition._meta["ui"] as Record<string, unknown>)["resourceUri"] === "string"
      )
    );

  if (hasUiMeta) {
    registerAppTool(server, definition.name, {
      ...config,
      _meta: definition._meta ?? {},
    }, handler);
    return;
  }

  server.registerTool(definition.name, config, handler);
};
