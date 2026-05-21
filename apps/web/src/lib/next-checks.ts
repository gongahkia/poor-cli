import type { AnalystFollowUp, BusinessDossier, NextCheck } from "@/types/dossier";

export const formatNextCheckInputLabel = (key: string): string => {
  const label = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());

  return label
    .replace(/\bUen\b/g, "UEN")
    .replace(/\bApi\b/g, "API")
    .replace(/\bId\b/g, "ID")
    .replace(/\bSg\b/g, "SG");
};

export const formatNextCheckInputValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "Not supplied";
  }
  if (typeof value === "string") {
    return value.trim() === "" ? "Empty string" : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? "None" : value.map(formatNextCheckInputValue).join(", ");
  }
  if (typeof value === "object") {
    const fieldCount = Object.keys(value).length;
    return fieldCount === 0 ? "Empty object" : `Structured input (${fieldCount} fields)`;
  }
  return String(value);
};

export const getNextCheckInputEntries = (input: Record<string, unknown>): [string, unknown][] => Object.entries(input);

export const formatNextCheckInputSummary = (input: Record<string, unknown>): string => {
  const entries = getNextCheckInputEntries(input);
  if (entries.length === 0) {
    return "No suggested input returned.";
  }
  return entries
    .map(([key, value]) => `${formatNextCheckInputLabel(key)}: ${formatNextCheckInputValue(value)}`)
    .join("; ");
};

export const followUpPriorityLabel = (priority: AnalystFollowUp["priority"]): string => {
  if (priority === "critical") return "Critical";
  if (priority === "recommended") return "Recommended";
  return "Optional";
};

export const followUpCategoryLabel = (category: AnalystFollowUp["category"]): string =>
  formatNextCheckInputLabel(category);

const legacyFollowUpFromNextCheck = (check: NextCheck, index: number): AnalystFollowUp => ({
  action: check.reason,
  category: "manual_confirmation",
  evidenceBasis: [{
    detail: "Legacy next-check item did not include the newer evidence-basis fields.",
    kind: "evidence_limitation",
    ref: `nextChecks.${index}`,
    source: check.tool,
  }],
  id: `legacy-next-check-${index + 1}`,
  input: check.input,
  priority: "recommended",
  reason: "Legacy next-check compatibility item.",
  tool: check.tool,
  whyThisMatters: "The follow-up is preserved for compatibility; review dossier gaps, source coverage, and limits before relying on it.",
});

export const getAnalystFollowUps = (dossier: BusinessDossier): AnalystFollowUp[] => {
  if (dossier.analystFollowUps !== undefined && dossier.analystFollowUps.length > 0) {
    return dossier.analystFollowUps;
  }
  return (dossier.nextChecks ?? []).map(legacyFollowUpFromNextCheck);
};

export const formatAnalystFollowUpInputSummary = (followUp: AnalystFollowUp): string =>
  followUp.input === undefined ? "No suggested input returned." : formatNextCheckInputSummary(followUp.input);
