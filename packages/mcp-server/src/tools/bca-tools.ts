import {
  BcaLicensedBuildersBaseSchema,
  BcaLicensedBuildersSchema,
  BcaRegisteredContractorsBaseSchema,
  BcaRegisteredContractorsSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../apis/bca/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleBcaLicensedBuilders = async (
  params: Readonly<{
    companyName?: string | undefined;
    uenNo?: string | undefined;
    className?: string | undefined;
    classCode?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getBcaLicensedBuilders(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const handleBcaRegisteredContractors = async (
  params: Readonly<{
    companyName?: string | undefined;
    uenNo?: string | undefined;
    workhead?: string | undefined;
    grade?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getBcaRegisteredContractors(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const bcaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_bca_licensed_builders",
    description: "Look up licensed builders by exact company name, UEN, builder class, or class code.",
    surface: "canonical",
    inputSchema: BcaLicensedBuildersBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBcaLicensedBuilders(validateInput(BcaLicensedBuildersSchema, input)),
  },
  {
    name: "sg_bca_registered_contractors",
    description: "Look up registered contractors by exact company name, UEN, workhead, or grade.",
    surface: "canonical",
    inputSchema: BcaRegisteredContractorsBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBcaRegisteredContractors(validateInput(BcaRegisteredContractorsSchema, input)),
  },
];
