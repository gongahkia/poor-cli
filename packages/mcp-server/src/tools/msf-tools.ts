import {
  formatResponse,
  MsfFamilyServicesInputSchema,
  MsfFamilyServicesSchema,
  MsfSocialServiceOfficesInputSchema,
  MsfSocialServiceOfficesSchema,
  MsfStudentCareServicesInputSchema,
  MsfStudentCareServicesSchema,
  resolveOutputFormat,
} from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { toDirectoryGeoFeatures } from "../apis/civic/utils.js";
import {
  getMsfFamilyServices,
  getMsfSocialServiceOffices,
  getMsfStudentCareServices,
} from "../apis/msf/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const renderDirectoryResult = (
  data: readonly Record<string, unknown>[],
  format: OutputFormat,
): string => {
  if (format === "geojson") {
    return formatResponse(toDirectoryGeoFeatures(data as never), "geojson");
  }
  return formatResponse(data, format);
};

export const handleMsfFamilyServices = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getMsfFamilyServices(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const handleMsfStudentCareServices = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    auditStatus?: string | undefined;
    scfaOnly?: boolean | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getMsfStudentCareServices(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const handleMsfSocialServiceOffices = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getMsfSocialServiceOffices(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const msfToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_msf_family_services",
    description: "Search MSF family service centres with optional postal-code or proximity filters.",
    surface: "canonical",
    inputSchema: MsfFamilyServicesInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleMsfFamilyServices(MsfFamilyServicesSchema.parse(input)),
  },
  {
    name: "sg_msf_student_care_services",
    description: "Search MSF student care services with optional postal-code, audit-status, SCFA, or proximity filters.",
    surface: "canonical",
    inputSchema: MsfStudentCareServicesInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleMsfStudentCareServices(MsfStudentCareServicesSchema.parse(input)),
  },
  {
    name: "sg_msf_social_service_offices",
    description: "Search MSF social service offices with optional postal-code or proximity filters.",
    surface: "canonical",
    inputSchema: MsfSocialServiceOfficesInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleMsfSocialServiceOffices(MsfSocialServiceOfficesSchema.parse(input)),
  },
];
