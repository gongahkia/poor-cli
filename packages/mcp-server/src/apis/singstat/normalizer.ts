import type { SingStatTableResponse, NormalizedRow } from "@swee-sg/shared";

export const normalizeTableData = (raw: SingStatTableResponse): NormalizedRow[] => {
  return raw.Data.row.flatMap((row) =>
    row.columns.map((col) => ({
      period: col.key,
      variable: row.rowText,
      value: isNaN(parseFloat(col.value)) ? col.value : parseFloat(col.value),
      unit: row.uoM,
      ...(row.footnote !== "" ? { footnote: row.footnote } : {}),
    })),
  );
};

export const detectUnit = (raw: SingStatTableResponse): string => {
  const firstRow = raw.Data.row[0];
  return firstRow?.uoM ?? "Unknown";
};
