import {
  BriefArtifactSchema,
} from "@swee-sg/shared";
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
const COUNTERPARTY_RESOLUTION_OUTPUT_SCHEMA = z.object({
  status: z.enum(["resolved", "needs_confirmation", "no_match"]),
}).passthrough();
const CDD_REPORT_OUTPUT_SCHEMA = z.object({
  status: z.string().optional(),
}).passthrough();

const MUTATING_TOOL_NAMES = new Set([
  "sg_cache_clear",
  "sg_key_set",
  "sg_key_delete",
  "sg_config_set",
]);

const BRIEF_TOOL_NAMES = new Set([
  "sg_business_dossier",
]);

const DILIGENCE_PROFILE_TOOL_NAMES = new Set([
  "sg_cdd_report",
  "sg_resolve_counterparty",
  "sg_query",
  "sg_business_dossier",
]);

const DILIGENCE_PROFILE_PREFIXES = [
  "sg_acra_",
  "sg_bca_",
  "sg_boa_",
  "sg_cea_",
  "sg_gebiz_",
  "sg_hsa_",
  "sg_hlb_",
  "sg_sanctions_",
  "sg_opencorporates_",
  "sg_adverse_",
  "sg_relationship_",
] as const;

const OUTPUT_SCHEMAS: Readonly<Record<string, z.ZodTypeAny>> = {
  sg_business_dossier: BRIEF_ARTIFACT_OUTPUT_SCHEMA,
  sg_cdd_report: CDD_REPORT_OUTPUT_SCHEMA,
  sg_query: QUERY_OUTPUT_SCHEMA,
  sg_resolve_counterparty: COUNTERPARTY_RESOLUTION_OUTPUT_SCHEMA,
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
  ema: "EMA",
  gov: "Gov",
  gebiz: "GeBIZ",
  hdb: "HDB",
  health: "Health",
  hlb: "HLB",
  hsa: "HSA",
  iras: "IRAS",
  key: "Key",
  lta: "LTA",
  mas: "MAS",
  moe: "MOE",
  moh: "MOH",
  law: "Law",
  mom: "MOM",
  msf: "MSF",
  nea: "NEA",
  nlb: "NLB",
  onemap: "OneMap",
  pa: "PA",
  pub: "PUB",
  query: "Query",
  sfa: "SFA",
  singstat: "SingStat",
  rss: "RSS",
  spf: "SPF",
  sportsg: "SportSG",
  stb: "STB",
  coe: "COE",
  ura: "URA",
  sg: "SG",
  splunk: "Splunk",
  swee: "Swee",
  pulse: "Pulse",
  shield: "Shield",
  hr: "2hr",
};

const toTitleToken = (token: string): string => {
  return TITLE_TOKENS[token] ?? token.charAt(0).toUpperCase() + token.slice(1);
};

export const inferToolTitle = (name: string): string => {
  return name
    .replace(/^(sg|swee)_/, "")
    .split("_")
    .map((token) => toTitleToken(token))
    .join(" ");
};

const matchesAnyPrefix = (name: string, prefixes: readonly string[]): boolean => {
  return prefixes.some((prefix) => name.startsWith(prefix));
};

const isDiligenceProfileTool = (name: string): boolean => {
  return DILIGENCE_PROFILE_TOOL_NAMES.has(name) || matchesAnyPrefix(name, DILIGENCE_PROFILE_PREFIXES);
};

export const inferToolSets = (name: string): readonly ToolSet[] => {
  const toolsets: ToolSet[] = [];

  if (name.startsWith("swee_pulse_")) {
    toolsets.push("public");
  } else if (name.startsWith("swee_shield_")) {
    toolsets.push("ops");
  } else if (name === "sg_query") {
    toolsets.push("query");
  } else if (name === "sg_health_check") {
    toolsets.push("health");
  } else if (BRIEF_TOOL_NAMES.has(name)) {
    toolsets.push("briefs");
  } else if (
    name.startsWith("sg_cache_")
    || name.startsWith("sg_key_")
    || name.startsWith("sg_config_")
    || name.startsWith("sg_trace_")
    || name.startsWith("sg_request_")
  ) {
    toolsets.push("ops");
  } else {
    toolsets.push("public");
  }

  if (isDiligenceProfileTool(name)) {
    toolsets.push("diligence");
  }
  return [...new Set(toolsets)];
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
