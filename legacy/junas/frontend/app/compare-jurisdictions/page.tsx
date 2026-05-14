"use client";
import { useState, useEffect } from "react";
import { listJurisdictions, listClauses, compareGlossaryTerm } from "../../lib/api-client";

type Jurisdiction = { id: string; name: string; short_name: string };
type Clause = { id: string; name: string; category: string; jurisdiction: string; description: string; standard: string; notes: string };

export default function CompareJurisdictionsPage() {
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set(["sg", "my"]));
  const [mode, setMode] = useState<"clauses" | "glossary">("clauses");
  const [query, setQuery] = useState("");
  const [clauseResults, setClauseResults] = useState<Record<string, Clause[]>>({});
  const [glossaryResults, setGlossaryResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { listJurisdictions().then(setJurisdictions).catch(() => {}); }, []);

  const toggle = (id: string) => {
    setSelected((prev) => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  };

  const search = async () => {
    if (!query.trim() || selected.size === 0) return;
    setLoading(true);
    try {
      if (mode === "clauses") {
        const results: Record<string, Clause[]> = {};
        await Promise.all(Array.from(selected).map(async (j) => {
          const data = await listClauses(query, j);
          results[j] = Array.isArray(data) ? data : [];
        }));
        setClauseResults(results);
        setGlossaryResults(null);
      } else {
        const data = await compareGlossaryTerm(query, Array.from(selected));
        setGlossaryResults(data);
        setClauseResults({});
      }
    } catch {}
    setLoading(false);
  };

  return (
    <div>
      <h2>Comparative Jurisdiction Analysis</h2>
      <p className="meta-line">Compare legal clauses or glossary terms across jurisdictions</p>
      {/* jurisdiction selector */}
      <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        {jurisdictions.map((j) => (
          <button key={j.id} type="button" onClick={() => toggle(j.id)} style={{ padding: "0.3rem 0.6rem", borderRadius: "0.5rem", border: selected.has(j.id) ? "2px solid #1d4ed8" : "1px solid #94a3b8", background: selected.has(j.id) ? "#dbeafe" : "#f8fafc", cursor: "pointer", fontSize: "0.82rem", fontWeight: selected.has(j.id) ? 700 : 400 }}>
            {j.short_name} ({j.name})
          </button>
        ))}
      </div>
      {/* mode selector */}
      <div style={{ display: "flex", gap: "0.35rem", marginBottom: "0.5rem" }}>
        {(["clauses", "glossary"] as const).map((m) => (
          <button key={m} type="button" onClick={() => setMode(m)} style={{ padding: "0.3rem 0.6rem", borderRadius: "0.5rem", border: mode === m ? "2px solid #1d4ed8" : "1px solid #94a3b8", background: mode === m ? "#dbeafe" : "#f8fafc", cursor: "pointer", fontSize: "0.82rem", textTransform: "capitalize" }}>{m}</button>
        ))}
      </div>
      {/* search */}
      <div style={{ display: "flex", gap: "0.4rem", marginBottom: "1rem" }}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder={mode === "clauses" ? "Search clause topic..." : "Enter glossary term..."} style={{ flex: 1, padding: "0.5rem", borderRadius: "0.5rem", border: "1px solid #94a3b8", font: "inherit" }} />
        <button type="button" onClick={search} disabled={loading} style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", background: "#0f172a", color: "#fff", cursor: loading ? "not-allowed" : "pointer", font: "inherit" }}>{loading ? "..." : "Compare"}</button>
      </div>
      {/* clause results: side by side */}
      {Object.keys(clauseResults).length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${selected.size}, 1fr)`, gap: "1rem" }}>
          {Array.from(selected).map((jId) => (
            <div key={jId}>
              <h3 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>{jurisdictions.find((j) => j.id === jId)?.name || jId}</h3>
              {(clauseResults[jId] || []).length === 0 ? <p className="meta-line">No matching clauses</p> : (
                <ul className="results-list">
                  {clauseResults[jId].map((c) => (
                    <li key={c.id} className="result-card">
                      <strong>{c.name}</strong>
                      <span className="badge muted" style={{ marginLeft: "0.3rem" }}>{c.category}</span>
                      <p className="meta-line" style={{ margin: "0.2rem 0" }}>{c.description}</p>
                      <p style={{ fontSize: "0.82rem", lineHeight: 1.5 }}>{c.standard}</p>
                      {c.notes && <p className="meta-line" style={{ fontSize: "0.75rem", borderTop: "1px solid #e2e8f0", paddingTop: "0.3rem", marginTop: "0.3rem" }}>{c.notes}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      {/* glossary results */}
      {glossaryResults && (
        <div>
          <h3>Glossary Comparison: &ldquo;{query}&rdquo;</h3>
          {glossaryResults.comparisons?.length > 0 ? (
            <table className="comparison-table">
              <thead><tr><th>Jurisdiction</th><th>Definition</th></tr></thead>
              <tbody>
                {glossaryResults.comparisons.map((c: any, i: number) => (
                  <tr key={i}><td><strong>{c.jurisdiction}</strong></td><td dangerouslySetInnerHTML={{ __html: c.definition || c.text || "Not found" }} /></tr>
                ))}
              </tbody>
            </table>
          ) : <p className="meta-line">No glossary results found across selected jurisdictions.</p>}
        </div>
      )}
    </div>
  );
}
