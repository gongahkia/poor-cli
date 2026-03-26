import { formatResponse, GeBIZTendersSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getGeBIZTenders } from "../apis/gebiz/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleGeBIZTenders = async (
  params: Readonly<{
    agency?: string | undefined;
    category?: string | undefined;
    supplierName?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getGeBIZTenders(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return { content: [{ type: "text", text }], structuredContent: { records: data } };
};

export const gebizToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_gebiz_tenders",
    description: "Search government procurement tenders and awards from GeBIZ via data.gov.sg.",
    surface: "canonical",
    inputSchema: GeBIZTendersSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = GeBIZTendersSchema.parse(input);
      return handleGeBIZTenders(parsed);
    },
  },
];
