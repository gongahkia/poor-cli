import { ChangeEvent, useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  BookmarkPlus,
  CheckCircle2,
  Database,
  ExternalLink,
  FileJson,
  FileSpreadsheet,
  Loader2,
  Play,
  RotateCw,
  Upload,
} from "lucide-react";

import { useToast } from "@/components/notifications/ToastProvider";
import { Button } from "@/components/ui/button";
import { parseBulkInput } from "@/lib/bulk";
import {
  buildDossierExportSummary,
  exportBulkCsv,
  exportBulkJson,
} from "@/lib/export/structured";
import { postGatewayJson } from "@/lib/api/client";
import { saveShortlistEntry } from "@/lib/shortlist";
import { persistAuditEvent, persistBulkJob, summarizeBulkRisk } from "@/lib/workspace-store";
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
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const fileInputId = useId();
  const parsed = useMemo(() => parseBulkInput(input), [input]);
  const { notify } = useToast();
  const visibleRows = useMemo(
    () => sortRows(filterRows(result?.rows ?? [], filter), sort),
    [filter, result?.rows, sort],
  );
  const riskSummary = useMemo(() => result === null ? null : summarizeBulkRisk(result), [result]);

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file === undefined) return;
    setSelectedFileName(file.name);
    setInput(await file.text());
    notify({ title: "File loaded", description: file.name, tone: "success" });
  };

  const executeBulk = async (items: { identifier: string }[], mode: "run" | "retry") => {
    setStatus("running");
    setError(null);
    if (mode === "run") setResult(null);
    try {
      const response = await postGatewayJson<BulkDossierResponse>("/api/v1/dude/bulk-dossiers", {
        items,
      });
      setResult(response);
      persistBulkJob(response);
      setStatus("idle");
      notify({
        title: mode === "retry" ? "Retry complete" : "Bulk check complete",
        description: `${response.executedCount} rows executed; ${response.parseErrors.length} parse errors.`,
        tone: response.parseErrors.length > 0 ? "warning" : "success",
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Bulk check failed.";
      setError(message);
      setStatus("error");
      notify({ title: "Bulk check failed", description: message, tone: "error" });
    }
  };

  const runBulk = async () => executeBulk(parsed.items, "run");

  const retryFailedRows = async () => {
    if (result === null) return;
    const retryItems = result.rows
      .filter((row) => row.status === "error" || row.upstreamFailure)
      .map((row) => ({ identifier: row.input }));
    if (retryItems.length === 0) {
      notify({ title: "No failed rows to retry", tone: "info" });
      return;
    }
    await executeBulk(retryItems, "retry");
  };

  const exportCsv = async () => {
    try {
      if (result === null) return;
      await exportBulkCsv(result.rows, result.generatedAt);
      persistAuditEvent({
        eventType: "export",
        permission: "export:run",
        input: { format: "bulk_csv", generatedAt: result.generatedAt },
        output: { rows: result.rows.length },
        metadata: { source: "bulk" },
      });
      notify({ title: "CSV export started", description: `${result.rows.length} rows.`, tone: "success" });
    } catch (error) {
      notify({ title: "CSV export failed", description: error instanceof Error ? error.message : "Unable to export CSV.", tone: "error" });
    }
  };

  const exportJson = async () => {
    try {
      if (result === null) return;
      await exportBulkJson(result.rows, result.generatedAt);
      persistAuditEvent({
        eventType: "export",
        permission: "export:run",
        input: { format: "bulk_json", generatedAt: result.generatedAt },
        output: { rows: result.rows.length },
        metadata: { source: "bulk" },
      });
      notify({ title: "JSON export started", description: `${result.rows.length} rows.`, tone: "success" });
    } catch (error) {
      notify({ title: "JSON export failed", description: error instanceof Error ? error.message : "Unable to export JSON.", tone: "error" });
    }
  };

  return (
    <section className="rounded-[22px] border border-border/90 bg-background p-4 shadow-sm sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Bulk checks</h2>
          <p className="mt-1 text-sm text-muted-foreground">Paste up to 200 UENs or company names, one per row, or upload a CSV.</p>
        </div>
        <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-border bg-muted/60 px-3 py-1.5 text-xs text-muted-foreground">
          <Database aria-hidden="true" className="h-3.5 w-3.5" />
          Workspace-backed
        </span>
      </div>

      <div className="mt-4 grid gap-3">
        <textarea
          className="min-h-36 resize-y rounded-[20px] border border-border bg-muted/25 px-4 py-3 text-base leading-6 text-foreground shadow-inner outline-none transition focus:border-ring focus:bg-background focus-visible:ring-0"
          onChange={(event) => setInput(event.target.value)}
          placeholder={"03591300B\nDBS BANK"}
          value={input}
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex h-12 min-w-0 max-w-sm items-center gap-3 rounded-[18px] border border-border bg-background px-3 text-sm">
            <input
              accept=".csv,text/csv,text/plain"
              aria-label="Upload CSV"
              className="sr-only"
              id={fileInputId}
              onChange={handleFile}
              type="file"
            />
            <label
              className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-muted px-3 py-1.5 font-medium text-foreground transition-colors hover:bg-muted/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              htmlFor={fileInputId}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  document.getElementById(fileInputId)?.click();
                }
              }}
              tabIndex={0}
            >
              <Upload aria-hidden="true" className="h-4 w-4" />
              Upload CSV
            </label>
            <span className="min-w-0 truncate text-muted-foreground">
              {selectedFileName ?? "No file chosen"}
            </span>
          </div>
          <Button
            className="h-12 gap-2 rounded-[18px] px-5"
            disabled={status === "running" || parsed.items.length === 0 || parsed.errors.length > 0}
            onClick={runBulk}
            type="button"
          >
            {status === "running" ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Play aria-hidden="true" className="h-4 w-4" />
            )}
            {status === "running" ? "Running" : "Run bulk check"}
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-3 py-1">
          <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" />
          {parsed.items.length} valid rows
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-3 py-1">
          <AlertCircle aria-hidden="true" className="h-3.5 w-3.5" />
          {parsed.errors.length} parse errors
        </span>
        {result === null ? null : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-3 py-1">
            <Play aria-hidden="true" className="h-3.5 w-3.5" />
            {result.executedCount} executed
          </span>
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
          {riskSummary === null ? null : (
            <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {[
                ["High risk", riskSummary.high],
                ["Medium", riskSummary.medium],
                ["Low", riskSummary.low],
                ["No risk", riskSummary.none],
                ["Gaps", riskSummary.gaps],
                ["Upstream", riskSummary.upstreamFailures],
              ].map(([label, value]) => (
                <div className="rounded-[18px] border border-border bg-background p-3" key={label}>
                  <p className="text-xs uppercase text-muted-foreground">{label}</p>
                  <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-2">
              <select
                className="h-10 rounded-[14px] border border-input bg-background px-3 text-sm"
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
                className="h-10 rounded-[14px] border border-input bg-background px-3 text-sm"
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
              <Button
                className="gap-2"
                disabled={status === "running" || !result.rows.some((row) => row.status === "error" || row.upstreamFailure)}
                onClick={() => void retryFailedRows()}
                type="button"
                variant="outline"
              >
                <RotateCw aria-hidden="true" className="h-4 w-4" />
                Retry failed
              </Button>
              <Button aria-label="Export bulk CSV" onClick={() => void exportCsv()} size="icon" title="Export CSV" type="button" variant="outline">
                <FileSpreadsheet aria-hidden="true" className="h-4 w-4" />
                <span className="sr-only">Export CSV</span>
              </Button>
              <Button aria-label="Export bulk JSON" onClick={() => void exportJson()} size="icon" title="Export JSON" type="button" variant="outline">
                <FileJson aria-hidden="true" className="h-4 w-4" />
                <span className="sr-only">Export JSON</span>
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto rounded-[20px] border border-border bg-background">
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
                          <Link className="inline-flex items-center gap-1 text-xs font-medium underline-offset-4 hover:underline" to={`/c/${encodeURIComponent(row.canonicalIdentifier)}`}>
                            <ExternalLink aria-hidden="true" className="h-3 w-3" />
                            Open
                          </Link>
                        )}
                        {row.dossier === undefined ? null : (
                          <button
                            className="inline-flex items-center gap-1 text-left text-xs font-medium underline-offset-4 hover:underline"
                            onClick={() => {
                              if (row.dossier !== undefined) {
                                saveShortlistEntry(buildDossierExportSummary(row.dossier));
                                notify({ title: "Saved to shortlist", description: row.entity ?? row.input, tone: "success" });
                              }
                            }}
                            type="button"
                          >
                            <BookmarkPlus aria-hidden="true" className="h-3 w-3" />
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
