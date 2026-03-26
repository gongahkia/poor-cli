import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getSchools } from "../apis/moe/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const MoeSchoolsSchema = z.object({
  level: z.string().min(1).optional().describe("PRIMARY, SECONDARY, JUNIOR COLLEGE, etc."),
  zone: z.string().min(1).optional().describe("NORTH, SOUTH, EAST, WEST"),
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const handleMoeSchools = async (
  params: Readonly<{
    level?: string;
    zone?: string;
    name?: string;
    limit?: number;
    format?: OutputFormat;
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
