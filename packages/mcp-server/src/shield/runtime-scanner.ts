import type { ShieldRiskLevel, ShieldRuntimeFinding, ToolResult, ToolResultContent } from "@swee-sg/shared";

type StringPattern = {
  readonly code: string;
  readonly severity: ShieldRiskLevel;
  readonly action: ShieldRuntimeFinding["action"];
  readonly message: string;
  readonly evidence: string;
  readonly pattern: RegExp;
  readonly replacement: string | ((match: string, ...groups: readonly string[]) => string);
};

type ScanValueResult = {
  readonly value: unknown;
  readonly findings: readonly ShieldRuntimeFinding[];
};

export type RuntimeScanResult = {
  readonly result: ToolResult;
  readonly findings: readonly ShieldRuntimeFinding[];
};

const REDACTION_PATTERNS: readonly StringPattern[] = [
  {
    code: "SECRET_ASSIGNMENT_REDACTED",
    severity: "high",
    action: "redacted",
    message: "Credential-shaped output was redacted before returning to the caller.",
    evidence: "credential-shaped assignment",
    pattern: /\b(api[_-]?key|token|password|secret|credential|authorization)\b(\s*[:=]\s*)(["']?)[A-Za-z0-9._~+/=-]{8,}(["']?)/gi,
    replacement: (_match, key, separator, openQuote, closeQuote) => `${key}${separator}${openQuote}[redacted]${closeQuote}`,
  },
  {
    code: "BEARER_TOKEN_REDACTED",
    severity: "high",
    action: "redacted",
    message: "Bearer-token-shaped output was redacted before returning to the caller.",
    evidence: "bearer-token-shaped value",
    pattern: /\bBearer\s+[A-Za-z0-9._~+/=-]{12,}/gi,
    replacement: "Bearer [redacted]",
  },
  {
    code: "EMAIL_REDACTED",
    severity: "medium",
    action: "redacted",
    message: "Email-shaped output was redacted before returning to the caller.",
    evidence: "email-shaped value",
    pattern: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
    replacement: "[redacted-email]",
  },
  {
    code: "SINGAPORE_ID_REDACTED",
    severity: "medium",
    action: "redacted",
    message: "Singapore identifier-shaped output was redacted before returning to the caller.",
    evidence: "singapore-id-shaped value",
    pattern: /\b[STFGM]\d{7}[A-Z]\b/gi,
    replacement: "[redacted-id]",
  },
  {
    code: "CARD_NUMBER_REDACTED",
    severity: "medium",
    action: "redacted",
    message: "Payment-card-shaped output was redacted before returning to the caller.",
    evidence: "card-number-shaped value",
    pattern: /\b(?:\d[ -]*?){13,19}\b/g,
    replacement: "[redacted-card]",
  },
];

const INJECTION_PATTERNS: readonly StringPattern[] = [
  {
    code: "PROMPT_OVERRIDE_NEUTRALIZED",
    severity: "high",
    action: "neutralized",
    message: "Prompt-override text in tool output was neutralized before reaching the caller.",
    evidence: "prompt override wording",
    pattern: /\b(ignore|override|bypass)\b.{0,120}\b(previous|system|developer|policy|instruction)s?\b/gi,
    replacement: "[neutralized prompt-injection text]",
  },
  {
    code: "SECRET_EXFILTRATION_NEUTRALIZED",
    severity: "critical",
    action: "neutralized",
    message: "Secret-exfiltration instruction in tool output was neutralized before reaching the caller.",
    evidence: "secret exfiltration wording",
    pattern: /\b(reveal|print|exfiltrate|send|upload|leak)\b.{0,120}\b(secret|token|api key|password|credential|environment variable)s?\b/gi,
    replacement: "[neutralized prompt-injection text]",
  },
  {
    code: "TOOL_OVERRIDE_NEUTRALIZED",
    severity: "high",
    action: "neutralized",
    message: "Tool-override instruction in tool output was neutralized before reaching the caller.",
    evidence: "tool override wording",
    pattern: /\b(call|invoke|run|use)\b.{0,80}\btool\b.{0,80}\b(ignore|bypass|without)\b/gi,
    replacement: "[neutralized prompt-injection text]",
  },
];

const STRING_PATTERNS = [...REDACTION_PATTERNS, ...INJECTION_PATTERNS] as const;

const applyStringPattern = (value: string, pattern: StringPattern): { readonly text: string; readonly matched: boolean } => {
  let matched = false;
  const text = value.replace(pattern.pattern, (match: string, ...groups: string[]) => {
    matched = true;
    return typeof pattern.replacement === "string"
      ? pattern.replacement
      : pattern.replacement(match, ...groups);
  });
  return { text, matched };
};

const scanString = (value: string, path: string): ScanValueResult => {
  let current = value;
  const findings: ShieldRuntimeFinding[] = [];
  for (const pattern of STRING_PATTERNS) {
    const result = applyStringPattern(current, pattern);
    if (!result.matched) continue;
    current = result.text;
    findings.push({
      severity: pattern.severity,
      code: pattern.code,
      message: pattern.message,
      path,
      action: pattern.action,
      evidence: pattern.evidence,
    });
  }
  return { value: current, findings };
};

const scanValue = (value: unknown, path: string): ScanValueResult => {
  if (typeof value === "string") return scanString(value, path);
  if (Array.isArray(value)) {
    const findings: ShieldRuntimeFinding[] = [];
    const items = value.map((item, index) => {
      const result = scanValue(item, `${path}[${index}]`);
      findings.push(...result.findings);
      return result.value;
    });
    return { value: items, findings };
  }
  if (value !== null && typeof value === "object") {
    const findings: ShieldRuntimeFinding[] = [];
    const entries = Object.entries(value as Readonly<Record<string, unknown>>).map(([key, nested]) => {
      const result = scanValue(nested, `${path}.${key}`);
      findings.push(...result.findings);
      return [key, result.value] as const;
    });
    return { value: Object.fromEntries(entries), findings };
  }
  return { value, findings: [] };
};

const scanTextContent = (content: Extract<ToolResultContent, { readonly type: "text" }>, index: number): {
  readonly content: ToolResultContent;
  readonly findings: readonly ShieldRuntimeFinding[];
} => {
  const result = scanString(content.text, `$.content[${index}].text`);
  return {
    content: { ...content, text: result.value as string },
    findings: result.findings,
  };
};

const scanResourceLinkContent = (content: Extract<ToolResultContent, { readonly type: "resource_link" }>, index: number): {
  readonly content: ToolResultContent;
  readonly findings: readonly ShieldRuntimeFinding[];
} => {
  const findings: ShieldRuntimeFinding[] = [];
  const scanField = (field: string, value: string | undefined): string | undefined => {
    if (value === undefined) return undefined;
    const result = scanString(value, `$.content[${index}].${field}`);
    findings.push(...result.findings);
    return result.value as string;
  };
  const title = scanField("title", content.title);
  const description = scanField("description", content.description);
  return {
    content: {
      ...content,
      uri: scanField("uri", content.uri) ?? content.uri,
      name: scanField("name", content.name) ?? content.name,
      ...(title === undefined ? {} : { title }),
      ...(description === undefined ? {} : { description }),
    },
    findings,
  };
};

export const scanToolResultForRuntimeFindings = (result: ToolResult): RuntimeScanResult => {
  const findings: ShieldRuntimeFinding[] = [];
  const content = result.content.map((item, index) => {
    const scanResult = item.type === "text"
      ? scanTextContent(item, index)
      : scanResourceLinkContent(item, index);
    findings.push(...scanResult.findings);
    return scanResult.content;
  });
  const structured = result.structuredContent === undefined
    ? null
    : scanValue(result.structuredContent, "$.structuredContent");
  const meta = result._meta === undefined ? null : scanValue(result._meta, "$._meta");
  if (structured !== null) findings.push(...structured.findings);
  if (meta !== null) findings.push(...meta.findings);

  return {
    result: {
      ...result,
      content,
      ...(structured === null ? {} : { structuredContent: structured.value as Readonly<Record<string, unknown>> }),
      ...(meta === null ? {} : { _meta: meta.value as Readonly<Record<string, unknown>> }),
    },
    findings,
  };
};
