import { ChangeEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { parseBulkInput } from "@/lib/bulk";
import {
  buildDossierExportSummary,
  exportBulkCsv,
  exportBulkJson,
} from "@/lib/export/structured";
import { postGatewayJson } from "@/lib/api/client";
import { saveShortlistEntry } from "@/lib/shortlist";
import type { BulkDossierResponse, BulkDossierRow } from "@/types/bulk";

type FilterMode = "all" | "risk" | "upstream" | "no_match" | "error";
type SortMode = "risk" | "confidence" | "gaps" | "input";

const riskRank: Record<BulkDossierRow["risk"], number> = {
  high: 3,
  medium: 2,
  low: 1,
  none: 0,
};

const confidenceRank = (value: string | null): number => {
  if (value === "high") return 3;
  if (value === "medium") return 2;
  if (value === "low") return 1;
  return 0;
};

function filterRows(rows: readonly BulkDossierRow[], filter: FilterMode): BulkDossierRow[] {
  if (filter === "risk") return rows.filter((row) => row.risk !== "none");
  if (filter === "upstream") return rows.filter((row) => row.upstreamFailure);
  if (filter === "no_match") return rows.filter((row) => row.status === "not_found");
  if (filter === "error") return rows.filter((row) => row.status === "error");
  return [...rows];
}

function sortRows(rows: readonly BulkDossierRow[], sort: SortMode): BulkDossierRow[] {
  return [...rows].sort((left, right) => {
    if (sort === "risk") return riskRank[right.risk] - riskRank[left.risk];
    if (sort === "confidence") return confidenceRank(right.confidence) - confidenceRank(left.confidence);
    if (sort === "gaps") return right.gapCodes.length - left.gapCodes.length;
    return left.input.localeCompare(right.input);
  });
}

export function BulkDiligence() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkDossierResponse | null>(null);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [sort, setSort] = useState<SortMode>("risk");
  const parsed = useMemo(() => parseBulkInput(input), [input]);
  const visibleRows = useMemo(
    () => sortRows(filterRows(result?.rows ?? [], filter), sort),
    [filter, result?.rows, sort],
  );

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file === undefined) return;
    setInput(await file.text());
  };

  const runBulk = async () => {
    setStatus("running");
    setError(null);
    setResult(null);
    try {
      const response = await postGatewayJson<BulkDossierResponse>("/api/v1/dude/bulk-dossiers", {
        items: parsed.items,
      });
      setResult(response);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk check failed.");
      setStatus("error");
    }
  };

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Bulk checks</h2>
          <p className="mt-1 text-sm text-muted-foreground">Paste UENs or company names, one per row, or upload a CSV.</p>
        </div>
        <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">No account</span>
      </div>

      <div className="mt-4 grid gap-3">
        <textarea
          className="min-h-28 resize-y rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onChange={(event) => setInput(event.target.value)}
          placeholder={"03591300B\nDBS BANK"}
          value={input}
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Input accept=".csv,text/csv,text/plain" aria-label="Upload CSV" className="max-w-sm" onChange={handleFile} type="file" />
          <Button
            disabled={status === "running" || parsed.items.length === 0 || parsed.errors.length > 0}
            onClick={runBulk}
            type="button"
          >
            {status === "running" ? "Running" : "Run bulk check"}
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span className="rounded-md bg-muted px-2 py-1">{parsed.items.length} valid rows</span>
        <span className="rounded-md bg-muted px-2 py-1">{parsed.errors.length} parse errors</span>
        {result === null ? null : (
          <span className="rounded-md bg-muted px-2 py-1">{result.executedCount} executed</span>
        )}
      </div>

      {parsed.errors.length === 0 ? null : (
        <ul className="mt-3 space-y-2 text-sm text-destructive">
          {parsed.errors.map((parseError) => (
            <li key={`${parseError.index}-${parseError.message}`}>
              Row {parseError.index + 1}: {parseError.message}
            </li>
          ))}
        </ul>
      )}

      {error === null ? null : <p className="mt-3 text-sm text-destructive">{error}</p>}

      {result === null ? null : (
        <div className="mt-5 space-y-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-2">
              <select
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                onChange={(event) => setFilter(event.target.value as FilterMode)}
                value={filter}
              >
                <option value="all">All rows</option>
                <option value="risk">Risk flags</option>
                <option value="upstream">Upstream failures</option>
                <option value="no_match">No match</option>
                <option value="error">Errors</option>
              </select>
              <select
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                onChange={(event) => setSort(event.target.value as SortMode)}
                value={sort}
              >
                <option value="risk">Sort by risk</option>
                <option value="confidence">Sort by confidence</option>
                <option value="gaps">Sort by gaps</option>
                <option value="input">Sort by input</option>
              </select>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => exportBulkCsv(result.rows, result.generatedAt)} type="button" variant="outline">
                Export CSV
              </Button>
              <Button onClick={() => exportBulkJson(result.rows, result.generatedAt)} type="button" variant="outline">
                Export JSON
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="min-w-[980px] w-full table-fixed text-left text-sm">
              <thead className="bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="w-48 px-3 py-2">Entity</th>
                  <th className="w-28 px-3 py-2">UEN</th>
                  <th className="w-28 px-3 py-2">Status</th>
                  <th className="w-24 px-3 py-2">Confidence</th>
                  <th className="w-24 px-3 py-2">Risk</th>
                  <th className="w-40 px-3 py-2">Modules</th>
                  <th className="w-44 px-3 py-2">Gaps</th>
                  <th className="w-32 px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr className="border-t border-border align-top" key={`${row.index}-${row.input}`}>
                    <td className="px-3 py-3">
                      <p className="truncate font-medium text-foreground">{row.entity ?? row.input}</p>
                      <p className="truncate text-xs text-muted-foreground">{row.input}</p>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">{row.uen ?? "-"}</td>
                    <td className="px-3 py-3">{row.entityStatus ?? row.status}</td>
                    <td className="px-3 py-3">{row.confidence ?? "-"}</td>
                    <td className="px-3 py-3">{row.risk}</td>
                    <td className="px-3 py-3">
                      <p className="line-clamp-2">{row.matchedModules.join(", ") || "-"}</p>
                    </td>
                    <td className="px-3 py-3">
                      <p className="line-clamp-2">{row.gapCodes.join(", ") || "-"}</p>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-col gap-2">
                        {row.canonicalIdentifier === null ? null : (
                          <Link className="text-xs font-medium underline-offset-4 hover:underline" to={`/c/${encodeURIComponent(row.canonicalIdentifier)}`}>
                            Open
                          </Link>
                        )}
                        {row.dossier === undefined ? null : (
                          <button
                            className="text-left text-xs font-medium underline-offset-4 hover:underline"
                            onClick={() => {
                              if (row.dossier !== undefined) {
                                saveShortlistEntry(buildDossierExportSummary(row.dossier));
                              }
                            }}
                            type="button"
                          >
                            Save
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="space-y-1 text-xs leading-5 text-muted-foreground">
            {result.limits.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
