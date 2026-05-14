import { formatLabel, formatRecordValue } from "@/lib/dossier";

type RecordTableProps = {
  records: Record<string, unknown>[];
};

const MAX_VISIBLE_CHARS = 96;

function getColumns(records: Record<string, unknown>[]): string[] {
  return Object.keys(records[0] ?? {});
}

function renderCell(key: string, value: unknown) {
  const formatted = formatRecordValue(key, value);
  const isEmpty = formatted === "-";
  const shouldTruncate = formatted.length > MAX_VISIBLE_CHARS;

  return (
    <span
      className={isEmpty ? "text-muted-foreground" : "block max-w-[18rem] truncate text-foreground"}
      title={shouldTruncate ? formatted : undefined}
    >
      {isEmpty ? "-" : formatted}
    </span>
  );
}

export function RecordTable({ records }: RecordTableProps) {
  if (records.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
        No matching records returned.
      </p>
    );
  }

  const columns = getColumns(records);

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th className="border-b border-border px-3 py-2 font-medium" key={column}>
                {formatLabel(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((record, index) => (
            <tr className="border-b border-border last:border-0" key={index}>
              {columns.map((column) => (
                <td className="align-top px-3 py-2" key={column}>
                  {renderCell(column, record[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
