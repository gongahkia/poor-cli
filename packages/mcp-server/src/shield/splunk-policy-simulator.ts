import { hashAuditValue, sanitizeAuditValue } from "./audit-store.js";

export type SplunkPolicyStatus = "allow" | "approval_required" | "deny";
export type SplunkPolicySeverity = "low" | "medium" | "high" | "critical";

export type SplunkSearchPolicyInput = {
  readonly query: string;
  readonly index?: string;
  readonly earliest?: string;
  readonly latest?: string;
  readonly limit?: number;
};

export type SplunkPolicyRule = {
  readonly code: string;
  readonly severity: SplunkPolicySeverity;
  readonly message: string;
};

export type SplunkPolicySimulation = {
  readonly status: SplunkPolicyStatus;
  readonly riskScore: number;
  readonly severity: SplunkPolicySeverity;
  readonly ruleCodes: readonly string[];
  readonly rules: readonly SplunkPolicyRule[];
  readonly requestedIndexes: readonly string[];
  readonly allowedIndexes: readonly string[];
  readonly suggestedSaferQuery: string;
  readonly limits: readonly string[];
};

export type SplunkRedTeamCorpusCase = {
  readonly id: string;
  readonly category: string;
  readonly label: string;
  readonly input: SplunkSearchPolicyInput;
  readonly expectedStatus: SplunkPolicyStatus;
};

const DISALLOWED_SPL = /\b(delete|outputlookup|collect|sendemail|script|map)\b/i;
const SPL_COMMAND_PATTERN = /\|\s*([A-Za-z][A-Za-z0-9_]*)/g;
const DEFAULT_ALLOWED_INDEXES = ["main", "security"] as const;

const severityRank: Readonly<Record<SplunkPolicySeverity, number>> = {
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

const maxSeverity = (rules: readonly SplunkPolicyRule[]): SplunkPolicySeverity => {
  return rules.reduce<SplunkPolicySeverity>(
    (current, rule) => severityRank[rule.severity] > severityRank[current] ? rule.severity : current,
    "low",
  );
};

export const readSplunkAllowedIndexes = (env: NodeJS.ProcessEnv = process.env): readonly string[] => (
  env["SPLUNK_MCP_ALLOWED_INDEXES"] ?? ""
)
  .split(",")
  .map((value) => value.trim())
  .filter((value) => value !== "");

export const extractSplunkQueryIndexes = (query: string): readonly string[] =>
  Array.from(query.matchAll(/\bindex\s*=\s*([A-Za-z0-9_.*-]+)/gi))
    .map((match) => match[1])
    .filter((value): value is string => value !== undefined && value.trim() !== "");

export const normalizeSplunkSearchRequest = (input: SplunkSearchPolicyInput): SplunkSearchPolicyInput => ({
  query: input.query.trim(),
  ...(input.index === undefined ? {} : { index: input.index.trim() }),
  ...(input.earliest === undefined ? {} : { earliest: input.earliest.trim() }),
  ...(input.latest === undefined ? {} : { latest: input.latest.trim() }),
  limit: input.limit ?? 50,
});

export const hashSplunkApprovalRequest = (input: SplunkSearchPolicyInput): string =>
  hashAuditValue(sanitizeAuditValue(normalizeSplunkSearchRequest(input)));

const rule = (code: string, severity: SplunkPolicySeverity, message: string): SplunkPolicyRule => ({
  code,
  severity,
  message,
});

const hasAnyTimeBound = (input: SplunkSearchPolicyInput): boolean =>
  input.earliest !== undefined || input.latest !== undefined || /\b(earliest|latest)\s*=/.test(input.query);

const buildSuggestedQuery = (
  input: SplunkSearchPolicyInput,
  allowedIndexes: readonly string[],
): string => {
  const normalized = normalizeSplunkSearchRequest(input);
  const requestedIndexes = extractSplunkQueryIndexes(normalized.query);
  const hasIndex = normalized.index !== undefined || requestedIndexes.length > 0;
  const index = normalized.index ?? requestedIndexes.find((value) => value !== "*") ?? allowedIndexes[0] ?? "<allowlisted_index>";
  const indexPrefix = hasIndex ? "" : `index=${index} `;
  const timeSuffix = hasAnyTimeBound(normalized) ? "" : " earliest=-24h latest=now";
  const limit = Math.min(normalized.limit ?? 50, 50);
  return `${indexPrefix}${normalized.query}${timeSuffix} | head ${limit}`.trim();
};

export const simulateSplunkSearchPolicy = (
  input: SplunkSearchPolicyInput,
  options: { readonly allowedIndexes?: readonly string[] } = {},
): SplunkPolicySimulation => {
  const normalized = normalizeSplunkSearchRequest(input);
  const allowedIndexes = options.allowedIndexes ?? readSplunkAllowedIndexes();
  const requestedIndexes = [
    ...extractSplunkQueryIndexes(normalized.query),
    ...(normalized.index === undefined ? [] : [normalized.index]),
  ];
  const rules: SplunkPolicyRule[] = [];

  if (DISALLOWED_SPL.test(normalized.query)) {
    rules.push(rule(
      "destructive_or_exfiltration_spl",
      "critical",
      "SPL contains a command blocked by the Swee Shield proxy.",
    ));
  }

  for (const index of requestedIndexes) {
    if (index === "*") {
      rules.push(rule("wildcard_index", "high", "Wildcard indexes require human approval."));
      continue;
    }
    if (allowedIndexes.length > 0 && !allowedIndexes.includes(index)) {
      rules.push(rule("index_not_allowlisted", "high", "Requested index is outside SPLUNK_MCP_ALLOWED_INDEXES."));
    }
  }

  if (requestedIndexes.length === 0 && normalized.index === undefined) {
    rules.push(rule("missing_explicit_index", "high", "Search has no explicit index."));
  }
  if (!hasAnyTimeBound(normalized)) {
    rules.push(rule("missing_time_bounds", "medium", "Search has no earliest/latest time bound."));
  }
  if ((normalized.limit ?? 50) > 50) {
    rules.push(rule("large_result_limit", "medium", "Search limit is above the approval-free demo cap of 50."));
  }

  const deny = rules.some((item) => item.code === "destructive_or_exfiltration_spl" || item.code === "index_not_allowlisted");
  const approval = !deny && rules.some((item) =>
    item.code === "wildcard_index"
    || item.code === "missing_explicit_index"
    || item.code === "missing_time_bounds"
    || item.code === "large_result_limit"
  );
  const status: SplunkPolicyStatus = deny ? "deny" : approval ? "approval_required" : "allow";
  const severity = maxSeverity(rules);
  const riskScore = status === "deny"
    ? 100
    : status === "approval_required"
      ? Math.max(60, Math.min(85, rules.length * 20 + severityRank[severity] * 15))
      : 10;

  return {
    status,
    riskScore,
    severity,
    ruleCodes: rules.length === 0 ? ["bounded_query"] : rules.map((item) => item.code),
    rules,
    requestedIndexes,
    allowedIndexes,
    suggestedSaferQuery: buildSuggestedQuery(normalized, allowedIndexes),
    limits: [
      "Simulator is deterministic and local-only; it does not prove live Splunk auth or data safety.",
      "Allowed-index checks use SPLUNK_MCP_ALLOWED_INDEXES when configured.",
    ],
  };
};

export const SPLUNK_RED_TEAM_CORPUS: readonly SplunkRedTeamCorpusCase[] = [
  {
    id: "clean-bounded",
    category: "allow",
    label: "Clean bounded search",
    input: { query: "index=security failed login", earliest: "-24h", latest: "now", limit: 25 },
    expectedStatus: "allow",
  },
  {
    id: "destructive-outputlookup",
    category: "deny",
    label: "Blocked outputlookup",
    input: { query: "index=security | outputlookup secrets.csv", earliest: "-24h", latest: "now", limit: 10 },
    expectedStatus: "deny",
  },
  {
    id: "bad-index",
    category: "deny",
    label: "Disallowed index",
    input: { query: "index=_internal error", earliest: "-24h", latest: "now", limit: 10 },
    expectedStatus: "deny",
  },
  {
    id: "wildcard-index",
    category: "approval_required",
    label: "Wildcard index",
    input: { query: "index=* error", earliest: "-24h", latest: "now", limit: 10 },
    expectedStatus: "approval_required",
  },
  {
    id: "missing-time",
    category: "approval_required",
    label: "Missing time bounds",
    input: { query: "index=security failed login", limit: 10 },
    expectedStatus: "approval_required",
  },
  {
    id: "large-limit",
    category: "approval_required",
    label: "Large result limit",
    input: { query: "index=security failed login", earliest: "-24h", latest: "now", limit: 75 },
    expectedStatus: "approval_required",
  },
];

export const buildSplunkRedTeamMatrix = (
  allowedIndexes: readonly string[] = DEFAULT_ALLOWED_INDEXES,
) => SPLUNK_RED_TEAM_CORPUS.map((item) => ({
  ...item,
  simulation: simulateSplunkSearchPolicy(item.input, { allowedIndexes }),
}));
