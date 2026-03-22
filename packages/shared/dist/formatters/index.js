export const formatJson = (data, pretty) => {
    return pretty !== false ? JSON.stringify(data, null, 2) : JSON.stringify(data);
};
export const formatMarkdown = (data) => {
    if (Array.isArray(data)) {
        if (data.length === 0)
            return "_No data_";
        const first = data[0];
        if (first === undefined)
            return "_No data_";
        const columns = Object.keys(first);
        const header = `| ${columns.join(" | ")} |`;
        const separator = `| ${columns.map(() => "---").join(" | ")} |`;
        const rows = data.map((row) => `| ${columns.map((col) => String(row[col] ?? "")).join(" | ")} |`);
        return [header, separator, ...rows].join("\n");
    }
    const entries = Object.entries(data);
    if (entries.length === 0)
        return "_No data_";
    return entries.map(([key, value]) => `**${key}**: ${String(value)}`).join("\n");
};
export const formatCsv = (rows, columns) => {
    if (rows.length === 0)
        return "";
    const first = rows[0];
    if (first === undefined)
        return "";
    const cols = columns ?? Object.keys(first);
    const escapeCsv = (val) => {
        const str = String(val ?? "");
        if (str.includes(",") || str.includes('"') || str.includes("\n")) {
            return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
    };
    const header = cols.join(",");
    const dataRows = rows.map((row) => cols.map((col) => escapeCsv(row[col])).join(","));
    return [header, ...dataRows].join("\n");
};
export const formatGeoJson = (features) => {
    return JSON.stringify({
        type: "FeatureCollection",
        features,
    }, null, 2);
};
export const formatStream = async function* (rows, format) {
    let first = true;
    let columns = [];
    if (format === "json") {
        yield "[\n";
    }
    for await (const row of rows) {
        if (first) {
            columns = Object.keys(row);
            if (format === "csv") {
                yield columns.join(",") + "\n";
            }
            else if (format === "markdown") {
                yield `| ${columns.join(" | ")} |\n`;
                yield `| ${columns.map(() => "---").join(" | ")} |\n`;
            }
            first = false;
        }
        if (format === "csv") {
            yield columns.map((col) => String(row[col] ?? "")).join(",") + "\n";
        }
        else if (format === "markdown") {
            yield `| ${columns.map((col) => String(row[col] ?? "")).join(" | ")} |\n`;
        }
        else if (format === "json") {
            yield (first ? "" : ",\n") + JSON.stringify(row);
        }
    }
    if (format === "json") {
        yield "\n]";
    }
};
export const formatResponse = (data, format) => {
    switch (format) {
        case "json":
            return formatJson(data, true);
        case "markdown":
            return formatMarkdown(data);
        case "csv":
            return formatCsv(data);
        case "geojson":
            return formatGeoJson(data);
    }
};
//# sourceMappingURL=index.js.map