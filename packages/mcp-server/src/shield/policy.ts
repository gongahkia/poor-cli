import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type {
  ShieldDecision,
  ShieldMode,
  ShieldPolicyDecision,
  ShieldRiskLevel,
  ShieldToolMetadata,
} from "@swee-sg/shared";

export type ShieldPolicyConfig = {
  readonly mode: ShieldMode;
  readonly allowTools?: readonly string[];
  readonly denyTools?: readonly string[];
  readonly warnTools?: readonly string[];
  readonly denyRiskAtOrAbove?: ShieldRiskLevel;
  readonly warnRiskAtOrAbove?: ShieldRiskLevel;
};

const RISK_ORDER: readonly ShieldRiskLevel[] = ["low", "medium", "high", "critical"];
const DEFAULT_POLICY: ShieldPolicyConfig = {
  mode: "observe",
  denyTools: [],
  warnTools: [],
  denyRiskAtOrAbove: "critical",
  warnRiskAtOrAbove: "high",
};

const parseMode = (value: string | undefined): ShieldMode => {
  if (value === "observe" || value === "enforce" || value === "kiasu") {
    return value;
  }
  return "observe";
};

const isRiskAtOrAbove = (risk: ShieldRiskLevel, threshold: ShieldRiskLevel | undefined): boolean => {
  if (threshold === undefined) return false;
  return RISK_ORDER.indexOf(risk) >= RISK_ORDER.indexOf(threshold);
};

const matchesPattern = (pattern: string, toolName: string): boolean => {
  if (pattern === "*") return true;
  if (pattern.endsWith("*")) return toolName.startsWith(pattern.slice(0, -1));
  return pattern === toolName;
};

const matchesAny = (patterns: readonly string[] | undefined, toolName: string): boolean =>
  (patterns ?? []).some((pattern) => matchesPattern(pattern, toolName));

const policyPath = (): string =>
  process.env["SWEE_SHIELD_POLICY_PATH"] ?? path.resolve(process.cwd(), "config/shield.policy.json");

export const loadShieldPolicy = (): ShieldPolicyConfig => {
  const configuredMode = parseMode(process.env["SWEE_SHIELD_MODE"]);
  const filePath = policyPath();
  if (!existsSync(filePath)) {
    return { ...DEFAULT_POLICY, mode: configuredMode };
  }

  const parsed = JSON.parse(readFileSync(filePath, "utf8")) as Partial<ShieldPolicyConfig>;
  return {
    ...DEFAULT_POLICY,
    ...parsed,
    mode: parseMode(process.env["SWEE_SHIELD_MODE"] ?? parsed.mode),
  };
};

export const buildShieldToolMetadata = (tool: {
  readonly name: string;
  readonly annotations?: {
    readonly readOnlyHint?: boolean | undefined;
    readonly destructiveHint?: boolean | undefined;
    readonly openWorldHint?: boolean | undefined;
  };
  readonly toolsets?: readonly string[];
}): ShieldToolMetadata => {
  const readOnly = tool.annotations?.readOnlyHint !== false && tool.annotations?.destructiveHint !== true;
  const source = tool.name.startsWith("swee_shield_")
    ? "swee-shield"
    : tool.name.startsWith("swee_pulse_")
      ? "swee-pulse"
      : tool.name.startsWith("sg_lta_")
        ? "lta"
        : tool.name.startsWith("sg_nea_")
          ? "nea"
          : tool.name.startsWith("sg_onemap_")
            ? "onemap"
            : tool.name.startsWith("sg_")
              ? "singapore-source"
              : "unknown";
  const operational = tool.toolsets?.includes("ops") === true;
  const riskLevel: ShieldRiskLevel = tool.annotations?.destructiveHint === true
    ? "critical"
    : operational || tool.name.startsWith("sg_key_") || tool.name.startsWith("sg_config_")
      ? "high"
      : tool.annotations?.openWorldHint === true
        ? "medium"
        : "low";

  return {
    toolName: tool.name,
    source,
    riskLevel,
    readOnly,
    openWorld: tool.annotations?.openWorldHint === true,
    authRequired: tool.name.startsWith("sg_lta_") || tool.name.startsWith("sg_ura_") || tool.name.startsWith("sg_onemap_"),
    tags: tool.toolsets ?? [],
  };
};

export const evaluateShieldPolicy = (params: {
  readonly toolName: string;
  readonly metadata?: ShieldToolMetadata;
  readonly policy?: ShieldPolicyConfig;
}): ShieldPolicyDecision => {
  const policy = params.policy ?? loadShieldPolicy();
  const metadata = params.metadata;
  const reasons: string[] = [];
  let decision: ShieldDecision = "allow";
  let riskLevel: ShieldRiskLevel = metadata?.riskLevel ?? "critical";

  if (metadata === undefined) {
    reasons.push("unknown_tool_metadata");
    decision = policy.mode === "kiasu" ? "deny" : "warn";
  } else {
    riskLevel = metadata.riskLevel;
  }

  if (matchesAny(policy.denyTools, params.toolName)) {
    reasons.push("policy_deny_list");
    decision = "deny";
  } else if (matchesAny(policy.warnTools, params.toolName)) {
    reasons.push("policy_warn_list");
    decision = decision === "deny" ? decision : "warn";
  }

  if (metadata !== undefined && matchesAny(policy.allowTools, params.toolName)) {
    reasons.push("policy_allow_list");
  } else if (isRiskAtOrAbove(riskLevel, policy.denyRiskAtOrAbove)) {
    reasons.push("risk_deny_threshold");
    decision = "deny";
  } else if (isRiskAtOrAbove(riskLevel, policy.warnRiskAtOrAbove)) {
    reasons.push("risk_warn_threshold");
    decision = decision === "deny" ? decision : "warn";
  }

  if (policy.mode === "observe" && decision === "deny") {
    reasons.push("observe_mode_no_block");
    decision = "warn";
  }

  return {
    mode: policy.mode,
    decision,
    toolName: params.toolName,
    riskLevel,
    reasonCodes: reasons.length === 0 ? ["default_allow"] : reasons,
    message: decision === "deny"
      ? `Swee Shield denied ${params.toolName}.`
      : decision === "warn"
        ? `Swee Shield allowed ${params.toolName} with warnings.`
        : `Swee Shield allowed ${params.toolName}.`,
  };
};
