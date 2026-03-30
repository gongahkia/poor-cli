import {
  BriefArtifactSchema,
} from "@sg-apis/shared";
import { z } from "zod";
import type { RegisteredToolDefinition, ToolSet } from "./tool-definition.js";

const STRUCTURED_OUTPUT_SCHEMA = z.object({}).passthrough();
const BRIEF_ARTIFACT_OUTPUT_SCHEMA = z.object({
  record: BriefArtifactSchema,
}).passthrough();
const QUERY_OUTPUT_SCHEMA = z.object({
  status: z.enum(["planned", "completed", "blocked", "unsupported", "failed"]),
  mode: z.enum(["execute", "plan"]),
}).passthrough();

const MUTATING_TOOL_NAMES = new Set([
  "sg_cache_clear",
  "sg_key_set",
  "sg_key_delete",
  "sg_config_set",
]);

const BRIEF_TOOL_NAMES = new Set([
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
]);

const OUTPUT_SCHEMAS: Readonly<Record<string, z.ZodTypeAny>> = {
  sg_business_dossier: BRIEF_ARTIFACT_OUTPUT_SCHEMA,
  sg_property_brief: BRIEF_ARTIFACT_OUTPUT_SCHEMA,
  sg_macro_brief: BRIEF_ARTIFACT_OUTPUT_SCHEMA,
  sg_transport_brief: BRIEF_ARTIFACT_OUTPUT_SCHEMA,
  sg_environment_brief: BRIEF_ARTIFACT_OUTPUT_SCHEMA,
  sg_query: QUERY_OUTPUT_SCHEMA,
};

const TITLE_TOKENS: Readonly<Record<string, string>> = {
  acra: "ACRA",
  api: "API",
  apis: "APIs",
  bca: "BCA",
  boa: "BOA",
  cache: "Cache",
  cea: "CEA",
  config: "Config",
  coords: "Coordinates",
  datagov: "data.gov.sg",
  ecda: "ECDA",
  gebiz: "GeBIZ",
  hdb: "HDB",
  health: "Health",
  hlb: "HLB",
  hsa: "HSA",
  key: "Key",
  lta: "LTA",
  mas: "MAS",
  moe: "MOE",
  moh: "MOH",
  mom: "MOM",
  msf: "MSF",
  nea: "NEA",
  onemap: "OneMap",
  pa: "PA",
  pub: "PUB",
  query: "Query",
  sfa: "SFA",
  singstat: "SingStat",
  sportsg: "SportSG",
  stb: "STB",
  ura: "URA",
  sg: "SG",
  hr: "2hr",
};

const toTitleToken = (token: string): string => {
  return TITLE_TOKENS[token] ?? token.charAt(0).toUpperCase() + token.slice(1);
};

export const inferToolTitle = (name: string): string => {
  return name
    .replace(/^sg_/, "")
    .split("_")
    .map((token) => toTitleToken(token))
    .join(" ");
};

export const inferToolSets = (name: string): readonly ToolSet[] => {
  if (name === "sg_query") {
    return ["query"];
  }
  if (name === "sg_health_check") {
    return ["health"];
  }
  if (BRIEF_TOOL_NAMES.has(name)) {
    return ["briefs"];
  }
  if (name.startsWith("sg_cache_") || name.startsWith("sg_key_") || name.startsWith("sg_config_")) {
    return ["ops"];
  }
  return ["public"];
};

export const inferToolOutputSchema = (name: string): z.ZodTypeAny | undefined => {
  if (MUTATING_TOOL_NAMES.has(name)) {
    return undefined;
  }
  return OUTPUT_SCHEMAS[name] ?? STRUCTURED_OUTPUT_SCHEMA;
};

export const inferToolAnnotations = (
  definition: Pick<RegisteredToolDefinition, "name" | "title">,
): NonNullable<RegisteredToolDefinition["annotations"]> => {
  const title = definition.title ?? inferToolTitle(definition.name);
  const toolsets = new Set(inferToolSets(definition.name));
  const readOnly = !toolsets.has("ops");
  const destructive = definition.name === "sg_cache_clear" || definition.name === "sg_key_delete";
  const idempotent = readOnly || definition.name === "sg_cache_clear" || definition.name === "sg_config_get" || definition.name === "sg_key_list";

  return {
    title,
    readOnlyHint: readOnly,
    destructiveHint: destructive,
    idempotentHint: idempotent,
    openWorldHint: !toolsets.has("ops"),
  };
};

export const hydrateToolDefinition = (definition: RegisteredToolDefinition): RegisteredToolDefinition => {
  const title = definition.title ?? inferToolTitle(definition.name);
  const annotations = {
    ...inferToolAnnotations({ name: definition.name, title }),
    ...definition.annotations,
  };

  return {
    ...definition,
    title,
    annotations,
    toolsets: definition.toolsets ?? inferToolSets(definition.name),
    ...(definition.outputSchema === undefined
      ? (() => {
          const inferredOutputSchema = inferToolOutputSchema(definition.name);
          return inferredOutputSchema === undefined ? {} : { outputSchema: inferredOutputSchema };
        })()
      : { outputSchema: definition.outputSchema }),
  };
};

export const isToolEnabled = (
  definition: Pick<RegisteredToolDefinition, "toolsets">,
  enabledToolsets: ReadonlySet<ToolSet>,
): boolean => {
  return (definition.toolsets ?? []).some((toolset) => enabledToolsets.has(toolset));
};
