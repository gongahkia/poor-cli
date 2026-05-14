"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type CheckResult = { rule_id: string; rule_name: string; status: string; details: string; severity: string };
type Summary = { total: number; passed: number; warnings: number; failed: number };

export default function CompliancePage() {
  const [text, setText] = useState("");
  const [results, setResults] = useState<CheckResult[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);

  const check = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch(`${API}/api/v1/compliance/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, jurisdiction: "sg" }),
      });
      const data = await resp.json();
      setResults(data.results || []);
      setSummary(data.summary || null);
    } catch {}
    setLoading(false);
  };

  const statusColor = (s: string) => s === "pass" ? "#16a34a" : s === "warning" ? "#d97706" : "#dc2626";
  const severityBadge = (s: string) => s === "high" ? "badge" : "badge muted";

  return (
    <div>
      <h2>Compliance Dashboard</h2>
      <p className="meta-line">Check documents against compliance rules (PDPA, Employment Act, contract basics)</p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste your legal document or contract text here..." rows={8} style={{ width: "100%", padding: "0.6rem", borderRadius: "0.5rem", border: "1px solid #94a3b8", font: "inherit", resize: "vertical", marginBottom: "0.5rem" }} />
      <button type="button" onClick={check} disabled={loading} style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", background: "#0f172a", color: "#fff", cursor: loading ? "not-allowed" : "pointer", font: "inherit", marginBottom: "1rem" }}>
        {loading ? "Checking..." : "Check Compliance"}
      </button>
      {summary && (
        <div className="summary-grid">
          <div className="result-card" style={{ textAlign: "center" }}><div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#16a34a" }}>{summary.passed}</div><div className="meta-line">Passed</div></div>
          <div className="result-card" style={{ textAlign: "center" }}><div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#d97706" }}>{summary.warnings}</div><div className="meta-line">Warnings</div></div>
          <div className="result-card" style={{ textAlign: "center" }}><div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#dc2626" }}>{summary.failed}</div><div className="meta-line">Failed</div></div>
        </div>
      )}
      {results.length > 0 && (
        <ul className="results-list">
          {results.map((r) => (
            <li key={r.rule_id} className="result-card">
              <div className="result-header">
                <span style={{ display: "inline-block", width: "0.7rem", height: "0.7rem", borderRadius: "999px", background: statusColor(r.status) }} />
                <strong>{r.rule_name}</strong>
                <span className={severityBadge(r.severity)} style={r.severity === "high" ? { borderColor: "#ef4444", color: "#b91c1c" } : undefined}>{r.severity}</span>
                <span style={{ textTransform: "uppercase", fontSize: "0.75rem", fontWeight: 700, color: statusColor(r.status) }}>{r.status}</span>
              </div>
              <p className="meta-line" style={{ margin: "0.2rem 0 0" }}>{r.details}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
