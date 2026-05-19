import type { ToolSet } from "./tool-definition.js";

export type TransportMode = "stdio" | "http";

export const ALL_TOOLSETS = [
  "public",
  "briefs",
  "query",
  "health",
  "ops",
  "diligence",
] as const satisfies readonly ToolSet[];

export type ToolsetProfileName = "public" | "cdd_report" | "diligence" | "ops";

export const TOOLSET_PROFILE_PRESETS: Readonly<Record<ToolsetProfileName, readonly ToolSet[]>> = {
  public: ["public", "briefs", "query", "health"],
  cdd_report: ["public", "briefs", "query", "health", "diligence"],
  diligence: ["public", "query", "health", "diligence"],
  ops: ["query", "health", "ops"],
} as const;

export const DEFAULT_TOOLSETS_BY_TRANSPORT: Readonly<Record<TransportMode, readonly ToolSet[]>> = {
  http: TOOLSET_PROFILE_PRESETS.public,
  stdio: ALL_TOOLSETS,
} as const;

const parseToolsetList = (configured: string): readonly ToolSet[] => {
  return configured
    .split(",")
    .map((value) => value.trim())
    .filter((value): value is typeof ALL_TOOLSETS[number] => (ALL_TOOLSETS as readonly string[]).includes(value));
};

const parseProfile = (value: string): ToolsetProfileName | null => {
  const normalized = value.trim().toLowerCase();
  if (normalized === "public" || normalized === "cdd_report" || normalized === "diligence" || normalized === "ops") {
    return normalized;
  }
  return null;
};

export const resolveEnabledToolsets = (options: {
  readonly transportMode: TransportMode;
  readonly configuredToolsets?: string;
  readonly configuredProfile?: string;
}): ReadonlySet<ToolSet> => {
  const configuredToolsets = options.configuredToolsets?.trim();
  if (configuredToolsets !== undefined && configuredToolsets !== "") {
    const toolsets = parseToolsetList(configuredToolsets);
    if (toolsets.length === 0) {
      throw new Error(`No valid toolsets found in "${configuredToolsets}".`);
    }
    return new Set(toolsets);
  }

  const configuredProfile = options.configuredProfile?.trim();
  if (configuredProfile !== undefined && configuredProfile !== "") {
    const profile = parseProfile(configuredProfile);
    if (profile === null) {
      throw new Error(`Unsupported tool profile "${configuredProfile}". Use public, cdd_report, diligence, or ops.`);
    }
    return new Set(TOOLSET_PROFILE_PRESETS[profile]);
  }

  return new Set(DEFAULT_TOOLSETS_BY_TRANSPORT[options.transportMode]);
};

export const TOOLSET_PROFILE_CATALOG = [
  {
    profile: "public",
    intent: "Default CDD profile for company search, cited dossier generation, public registry reads, and health checks.",
    toolsets: TOOLSET_PROFILE_PRESETS.public,
  },
  {
    profile: "cdd_report",
    intent: "Full analyst report profile with public registries, business dossier briefs, sg_query routing, and supplemental diligence evidence.",
    toolsets: TOOLSET_PROFILE_PRESETS.cdd_report,
  },
  {
    profile: "diligence",
    intent: "Least-privilege direct-tool profile for company/UEN diligence and supplemental review evidence.",
    toolsets: TOOLSET_PROFILE_PRESETS.diligence,
  },
  {
    profile: "ops",
    intent: "Operational profile for runtime health, cache, key, config, trace, request lookup, and sg_query diagnostics.",
    toolsets: TOOLSET_PROFILE_PRESETS.ops,
  },
] as const;
