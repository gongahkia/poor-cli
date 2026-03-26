import { formatResponse, MoeSchoolsSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getSchools } from "../apis/moe/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleMoeSchools = async (
  params: Readonly<{
    level?: string | undefined;
    zone?: string | undefined;
    name?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getSchools(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return { content: [{ type: "text", text }], structuredContent: { records: data } };
};

export const moeToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_moe_schools",
    description: "Search Singapore schools from MOE directory via data.gov.sg, filtered by level, zone, or name.",
    surface: "canonical",
    inputSchema: MoeSchoolsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = MoeSchoolsSchema.parse(input);
      return handleMoeSchools(parsed);
    },
  },
];
