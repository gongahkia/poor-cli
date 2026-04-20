import type { ToolSet } from "./tool-definition.js";

export type TransportMode = "stdio" | "http";

export const ALL_TOOLSETS = [
  "public",
  "briefs",
  "query",
  "health",
  "ops",
  "diligence",
  "property",
] as const satisfies readonly ToolSet[];

export type ToolsetProfileName = "public" | "diligence" | "property" | "ops";

export const TOOLSET_PROFILE_PRESETS: Readonly<Record<ToolsetProfileName, readonly ToolSet[]>> = {
  public: ["public", "briefs", "query", "health"],
  diligence: ["public", "query", "health", "diligence"],
  property: ["public", "query", "health", "property"],
  ops: ["public", "query", "health", "ops"],
} as const;

export const DEFAULT_TOOLSETS_BY_TRANSPORT: Readonly<Record<TransportMode, readonly ToolSet[]>> = {
  http: TOOLSET_PROFILE_PRESETS.public,
  stdio: ALL_TOOLSETS,
} as const;

const parseToolsetList = (configured: string): readonly ToolSet[] => {
  return configured
    .split(",")
    .map((value) => value.trim())
    .filter((value): value is ToolSet => ALL_TOOLSETS.includes(value as ToolSet));
};

const parseProfile = (value: string): ToolsetProfileName | null => {
  const normalized = value.trim().toLowerCase();
  if (normalized === "public" || normalized === "diligence" || normalized === "property" || normalized === "ops") {
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
      throw new Error(`Unsupported tool profile "${configuredProfile}". Use public, diligence, property, or ops.`);
    }
    return new Set(TOOLSET_PROFILE_PRESETS[profile]);
  }

  return new Set(DEFAULT_TOOLSETS_BY_TRANSPORT[options.transportMode]);
};

export const TOOLSET_PROFILE_CATALOG = [
  {
    profile: "public",
    intent: "Default host profile for broad read-only discovery plus bounded briefs and query routing.",
    toolsets: TOOLSET_PROFILE_PRESETS.public,
  },
  {
    profile: "diligence",
    intent: "Least-privilege profile for registry and compliance workflows.",
    toolsets: TOOLSET_PROFILE_PRESETS.diligence,
  },
  {
    profile: "property",
    intent: "Least-privilege profile for property, geospatial, transport, and environment workflows.",
    toolsets: TOOLSET_PROFILE_PRESETS.property,
  },
  {
    profile: "ops",
    intent: "Operational profile that enables cache, key, and config mutation tools.",
    toolsets: TOOLSET_PROFILE_PRESETS.ops,
  },
] as const;
