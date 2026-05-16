import { ApiError } from "@dude/shared";

const parseDisabledSet = (envKey: string): ReadonlySet<string> => {
  const raw = process.env[envKey];
  if (raw === undefined || raw.trim() === "") {
    return new Set();
  }
  return new Set(
    raw
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter((value) => value.length > 0),
  );
};

const isDisabled = (disabled: ReadonlySet<string>, id: string): boolean => {
  const normalized = id.trim().toLowerCase();
  return disabled.has("*") || disabled.has(normalized);
};

const throwDisabledError = (params: {
  tool: string;
  envKey: "SG_APIS_DISABLED_FAMILIES" | "SG_APIS_DISABLED_STREAMS";
  id: string;
  noun: "family" | "stream";
}): never => {
  throw new ApiError({
    apiName: "surface-control",
    source: "surface-control",
    tool: params.tool,
    statusCode: 503,
    code: "SURFACE_DISABLED",
    retryable: false,
    message: `The ${params.noun} '${params.id}' is disabled by ${params.envKey}.`,
    suggestedAction: `Remove '${params.id}' from ${params.envKey} (or clear the env var) to re-enable this ${params.noun}.`,
    details: {
      envKey: params.envKey,
      id: params.id,
      kind: params.noun,
    },
  });
};

export const assertFamilyEnabled = (
  familyId: string,
  toolName: string,
): void => {
  const disabledFamilies = parseDisabledSet("SG_APIS_DISABLED_FAMILIES");
  if (isDisabled(disabledFamilies, familyId)) {
    throwDisabledError({
      tool: toolName,
      envKey: "SG_APIS_DISABLED_FAMILIES",
      id: familyId,
      noun: "family",
    });
  }
};

export const assertStreamEnabled = (
  streamId: string,
  toolName: string,
): void => {
  const disabledStreams = parseDisabledSet("SG_APIS_DISABLED_STREAMS");
  if (isDisabled(disabledStreams, streamId)) {
    throwDisabledError({
      tool: toolName,
      envKey: "SG_APIS_DISABLED_STREAMS",
      id: streamId,
      noun: "stream",
    });
  }
};
