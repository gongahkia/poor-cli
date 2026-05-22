import type { MasRecord, NormalizedMasRecord } from "@swee-sg/shared";

export const normalizeMasDate = (dateStr: string): string => {
  if (/^\d{4}-\d{2}$/.test(dateStr)) {
    return `${dateStr}-01T00:00:00+08:00`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return `${dateStr}T00:00:00+08:00`;
  }
  return dateStr;
};

export const normalizeMasRecord = (raw: MasRecord): NormalizedMasRecord => {
  const normalized: Record<string, string | number> = {
    date: normalizeMasDate(raw.end_of_day),
  };

  for (const [key, value] of Object.entries(raw)) {
    if (key === "_id" || key === "end_of_day" || key === "timestamp") continue;
    if (typeof value === "string") {
      const num = parseFloat(value);
      normalized[key] = isNaN(num) ? value : num;
    } else if (typeof value === "number") {
      normalized[key] = value;
    }
  }

  return normalized as NormalizedMasRecord;
};
