export type ParsedBulkInput = {
  items: { identifier: string }[];
  errors: {
    index: number;
    input: string;
    message: string;
  }[];
};

const MAX_LOCAL_ROWS = 25;

const normalizeIdentifier = (value: string): string =>
  value
    .trim()
    .replace(/^"|"$/g, "")
    .trim();

const splitCsvLine = (line: string): string[] => {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === "\"" && line[index + 1] === "\"") {
      current += "\"";
      index += 1;
    } else if (char === "\"") {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      cells.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current);
  return cells;
};

const parseLines = (text: string): string[] => {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];

  const firstCells = splitCsvLine(lines[0] ?? "").map((cell) => cell.trim().toLowerCase());
  const identifierColumn = firstCells.findIndex((cell) =>
    cell === "identifier" || cell === "uen" || cell === "company" || cell === "company name" || cell === "entity",
  );
  const dataLines = identifierColumn >= 0 ? lines.slice(1) : lines;

  return dataLines.map((line) => {
    const cells = splitCsvLine(line);
    return normalizeIdentifier(cells[identifierColumn >= 0 ? identifierColumn : 0] ?? line);
  });
};

export function parseBulkInput(text: string): ParsedBulkInput {
  const identifiers = parseLines(text);
  const errors: ParsedBulkInput["errors"] = [];
  const items: ParsedBulkInput["items"] = [];

  identifiers.slice(0, MAX_LOCAL_ROWS).forEach((identifier, index) => {
    if (identifier === "") {
      errors.push({ index, input: identifier, message: "Identifier is required." });
      return;
    }
    if (identifier.length > 128) {
      errors.push({ index, input: identifier, message: "Identifier must be 128 characters or fewer." });
      return;
    }
    items.push({ identifier });
  });

  if (identifiers.length > MAX_LOCAL_ROWS) {
    errors.push({
      index: MAX_LOCAL_ROWS,
      input: String(identifiers.length),
      message: `Only the first ${MAX_LOCAL_ROWS} rows can be checked in one batch.`,
    });
  }

  return { errors, items };
}
