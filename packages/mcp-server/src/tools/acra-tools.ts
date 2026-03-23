import {
  AcraEntitiesBaseSchema,
  AcraEntitiesSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getAcraEntities } from "../apis/acra/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleAcraEntities = async (
  params: Readonly<{
    entityName?: string | undefined;
    uen?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getAcraEntities(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const acraToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_acra_entities",
    description: "Look up ACRA corporate-entity records by exact entity name or UEN across the official sharded public registry.",
    surface: "canonical",
    inputSchema: AcraEntitiesBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleAcraEntities(validateInput(AcraEntitiesSchema, input)),
  },
];
