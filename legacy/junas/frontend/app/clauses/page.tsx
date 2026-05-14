"use client";
import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Clause = { id: string; name: string; category: string; jurisdiction: string; description: string; standard: string; aggressive: string; balanced: string; protective: string; notes: string };
type Tone = "standard" | "aggressive" | "balanced" | "protective";

export default function ClausesPage() {
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Clause | null>(null);
  const [tone, setTone] = useState<Tone>("standard");

  useEffect(() => {
    fetch(`${API}/api/v1/clauses?query=${encodeURIComponent(query)}`)
      .then((r) => r.json()).then(setClauses).catch(() => {});
  }, [query]);

  return (
    <div>
      <h2>Clause Library</h2>
      <p className="meta-line">Legal clauses with tone variants (standard, aggressive, balanced, protective)</p>
      <input placeholder="Search clauses..." value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: "100%", padding: "0.5rem", borderRadius: "0.5rem", border: "1px solid #94a3b8", marginBottom: "1rem", font: "inherit" }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <div>
          <ul className="results-list">
            {clauses.map((c) => (
              <li key={c.id} className="result-card" style={{ cursor: "pointer", borderColor: selected?.id === c.id ? "#3b82f6" : undefined }} onClick={() => { setSelected(c); setTone("standard"); }}>
                <div className="result-header">
                  <strong>{c.name}</strong>
                  <span className="badge muted">{c.category}</span>
                  <span className="badge">{c.jurisdiction}</span>
                </div>
                <p className="meta-line" style={{ margin: "0.3rem 0 0" }}>{c.description}</p>
              </li>
            ))}
          </ul>
        </div>
        <div>
          {selected ? (
            <div className="result-card">
              <h3 style={{ margin: "0 0 0.5rem" }}>{selected.name}</h3>
              <div style={{ display: "flex", gap: "0.3rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
                {(["standard", "aggressive", "balanced", "protective"] as Tone[]).map((t) => (
                  <button key={t} type="button" onClick={() => setTone(t)} style={{ padding: "0.3rem 0.6rem", borderRadius: "0.5rem", border: tone === t ? "2px solid #1d4ed8" : "1px solid #94a3b8", background: tone === t ? "#dbeafe" : "#f8fafc", cursor: "pointer", fontWeight: tone === t ? 700 : 400, textTransform: "capitalize" }}>
                    {t}
                  </button>
                ))}
              </div>
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, marginBottom: "0.75rem" }}>{selected[tone]}</div>
              {selected.notes && <p className="meta-line" style={{ borderTop: "1px solid #e2e8f0", paddingTop: "0.5rem" }}><strong>Notes:</strong> {selected.notes}</p>}
            </div>
          ) : (
            <div className="result-card"><p className="meta-line">Select a clause to view its tone variants</p></div>
          )}
        </div>
      </div>
    </div>
  );
}
