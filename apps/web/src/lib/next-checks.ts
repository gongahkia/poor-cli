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
