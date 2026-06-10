import type { ShieldScannerFinding } from "@swee-sg/shared";

type ScannableTool = {
  readonly name: string;
  readonly title?: string;
  readonly description: string;
};

const POISON_PATTERNS = [
  {
    code: "PROMPT_OVERRIDE",
    pattern: /\b(ignore|override|bypass)\b.{0,80}\b(previous|system|developer|policy|instruction)s?\b/i,
    message: "Tool text appears to instruct a model to ignore higher-priority instructions.",
  },
  {
    code: "SECRET_EXFILTRATION",
    pattern: /\b(reveal|print|exfiltrate|send|upload|leak)\b.{0,80}\b(secret|token|api key|password|credential|environment variable)s?\b/i,
    message: "Tool text appears to request credential or secret disclosure.",
  },
  {
    code: "UNBOUNDED_REMOTE_FETCH",
    pattern: /\b(fetch|curl|wget|post|send)\b.{0,80}\b(http|url|webhook|remote server)\b/i,
    message: "Tool text appears to request unbounded remote network activity.",
  },
] as const;

export const scanToolForPoisoning = (tool: ScannableTool): readonly ShieldScannerFinding[] => {
  const text = [tool.title, tool.description].filter(Boolean).join("\n");
  return POISON_PATTERNS.flatMap((definition) => {
    const match = definition.pattern.exec(text);
    if (match === null) return [];
    return [{
      toolName: tool.name,
      severity: definition.code === "SECRET_EXFILTRATION" ? "critical" : "high",
      code: definition.code,
      message: definition.message,
      evidence: match[0].slice(0, 160),
    } satisfies ShieldScannerFinding];
  });
};

export const scanToolCatalogForPoisoning = (
  tools: readonly ScannableTool[],
): readonly ShieldScannerFinding[] => tools.flatMap((tool) => scanToolForPoisoning(tool));
