import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

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
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Local shortlist</h2>
          <p className="mt-1 text-sm text-muted-foreground">Saved in this browser only.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={entries.length === 0} onClick={() => exportShortlistCsv(entries)} type="button" variant="outline">
            Export CSV
          </Button>
          <Button disabled={entries.length === 0} onClick={() => void exportShortlistJson(entries)} type="button" variant="outline">
            Export JSON
          </Button>
          <Button disabled={entries.length === 0} onClick={() => setEntries(clearShortlist())} type="button" variant="outline">
            Clear
          </Button>
        </div>
      </div>

      {entries.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No saved counterparties.</p>
      ) : (
        <div className="mt-4 grid gap-2">
          {entries.map((entry) => (
            <article className="rounded-md border border-border p-3" key={entry.canonicalIdentifier}>
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
                  className="text-xs font-medium text-muted-foreground underline-offset-4 hover:underline"
                  onClick={() => setEntries(removeShortlistEntry(entry.canonicalIdentifier))}
                  type="button"
                >
                  Remove
                </button>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-md bg-muted px-2 py-1">Risk: {entry.risk}</span>
                <span className="rounded-md bg-muted px-2 py-1">Confidence: {entry.confidence ?? "-"}</span>
                <span className="rounded-md bg-muted px-2 py-1">Gaps: {entry.gapCodes.length}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
