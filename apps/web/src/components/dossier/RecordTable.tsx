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

function renderRecordValue(key: string, value: unknown) {
  const formatted = formatRecordValue(key, value);
  const isEmpty = formatted === "-";

  return (
    <span className={isEmpty ? "text-muted-foreground" : "break-words text-foreground"}>
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
  const useRecordGrid = columns.length > 8;
  const recordGridClassName = useRecordGrid
    ? records.length > 1
      ? "grid gap-3 lg:grid-cols-[repeat(2,minmax(0,1fr))]"
      : "grid gap-3"
    : "grid gap-3 md:hidden";

  return (
    <>
      <div className={recordGridClassName}>
        {records.map((record, index) => (
          <article className="rounded-md border border-border bg-background p-3" key={index}>
            {records.length > 1 ? (
              <p className="mb-3 text-xs font-medium uppercase text-muted-foreground">Record {index + 1}</p>
            ) : null}
            <dl
              className={useRecordGrid
                ? "grid gap-x-5 gap-y-2 md:grid-cols-[repeat(2,minmax(0,1fr))] xl:grid-cols-[repeat(3,minmax(0,1fr))]"
                : "grid gap-2"}
            >
              {columns.map((column) => (
                <div className="min-w-0 border-b border-border pb-2 last:border-0 last:pb-0" key={column}>
                  <dt className="text-xs font-medium uppercase text-muted-foreground">{formatLabel(column)}</dt>
                  <dd className="mt-1 text-sm leading-6">{renderRecordValue(column, record[column])}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>

      {useRecordGrid ? null : (
        <div className="hidden min-w-0 max-w-full overflow-hidden rounded-md border border-border md:block">
          <div className="max-w-full overflow-x-auto">
            <table className="w-max min-w-full border-collapse text-left text-sm">
              <thead className="bg-muted/70 text-xs uppercase text-muted-foreground">
                <tr>
                  {columns.map((column) => (
                    <th className="whitespace-nowrap border-b border-border px-3 py-2 font-medium" key={column}>
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
        </div>
      )}
    </>
  );
}
