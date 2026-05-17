import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileJson, FileSpreadsheet, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  exportShortlistCsv,
  exportShortlistJson,
} from "@/lib/export/structured";
import {
  clearShortlist,
  getShortlist,
  removeShortlistEntry,
} from "@/lib/shortlist";
import type { ShortlistEntry } from "@/types/bulk";

export function ShortlistPanel() {
  const [entries, setEntries] = useState<ShortlistEntry[]>(() => getShortlist());

  useEffect(() => {
    const sync = () => setEntries(getShortlist());
    window.addEventListener("storage", sync);
    window.addEventListener("dude-shortlist-change", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("dude-shortlist-change", sync);
    };
  }, []);

  return (
    <section className="rounded-[22px] border border-border/90 bg-background p-4 shadow-sm sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Local shortlist</h2>
          <p className="mt-1 text-sm text-muted-foreground">Saved in this browser only.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            aria-label="Export shortlist CSV"
            className="h-11 rounded-[16px]"
            disabled={entries.length === 0}
            onClick={() => exportShortlistCsv(entries)}
            size="icon"
            title="Export CSV"
            type="button"
            variant="outline"
          >
            <FileSpreadsheet aria-hidden="true" className="h-4 w-4" />
            <span className="sr-only">Export CSV</span>
          </Button>
          <Button
            aria-label="Export shortlist JSON"
            className="h-11 rounded-[16px]"
            disabled={entries.length === 0}
            onClick={() => void exportShortlistJson(entries)}
            size="icon"
            title="Export JSON"
            type="button"
            variant="outline"
          >
            <FileJson aria-hidden="true" className="h-4 w-4" />
            <span className="sr-only">Export JSON</span>
          </Button>
          <Button
            aria-label="Clear shortlist"
            className="h-11 rounded-[16px]"
            disabled={entries.length === 0}
            onClick={() => setEntries(clearShortlist())}
            size="icon"
            title="Clear shortlist"
            type="button"
            variant="outline"
          >
            <Trash2 aria-hidden="true" className="h-4 w-4" />
            <span className="sr-only">Clear</span>
          </Button>
        </div>
      </div>

      {entries.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No saved counterparties.</p>
      ) : (
        <div className="mt-4 grid gap-2">
          {entries.map((entry) => (
            <article className="rounded-[18px] border border-border bg-muted/20 p-3" key={entry.canonicalIdentifier}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <Link
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                    to={`/c/${encodeURIComponent(entry.canonicalIdentifier)}`}
                  >
                    {entry.entity ?? entry.canonicalIdentifier}
                  </Link>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">{entry.uen ?? entry.canonicalIdentifier}</p>
                </div>
                <button
                  aria-label={`Remove ${entry.entity ?? entry.canonicalIdentifier}`}
                  className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground underline-offset-4 hover:underline"
                  onClick={() => setEntries(removeShortlistEntry(entry.canonicalIdentifier))}
                  type="button"
                >
                  <X aria-hidden="true" className="h-3 w-3" />
                  Remove
                </button>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-full border border-border bg-background px-2.5 py-1">Risk: {entry.risk}</span>
                <span className="rounded-full border border-border bg-background px-2.5 py-1">Confidence: {entry.confidence ?? "-"}</span>
                <span className="rounded-full border border-border bg-background px-2.5 py-1">Gaps: {entry.gapCodes.length}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
