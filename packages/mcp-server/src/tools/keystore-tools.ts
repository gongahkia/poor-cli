import { validateInput, KeySetSchema, KeyDeleteSchema, Keystore, formatResponse } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const keystore = new Keystore();

export const keystoreToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_key_set",
    description: "Store an API key for a Singapore government API.",
    surface: "operational",
    inputSchema: KeySetSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { apiName, key } = validateInput(KeySetSchema, input);
      keystore.setKey(apiName, key);
      return { content: [{ type: "text", text: `API key stored for ${apiName}.` }] };
    },
  },

  {
    name: "sg_key_list",
    description: "List all stored API keys (values are masked).",
    surface: "operational",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const keys = keystore.listKeys();
      if (keys.length === 0) {
        return { content: [{ type: "text", text: "No API keys stored." }] };
      }
      const text = formatResponse(keys as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  },

  {
    name: "sg_key_delete",
    description: "Delete a stored API key.",
    surface: "operational",
    inputSchema: KeyDeleteSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { apiName } = validateInput(KeyDeleteSchema, input);
      const deleted = keystore.deleteKey(apiName);
      return { content: [{ type: "text", text: deleted ? `API key deleted for ${apiName}.` : `No API key found for ${apiName}.` }] };
    },
  },
];
