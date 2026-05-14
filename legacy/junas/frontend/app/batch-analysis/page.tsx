"use client";
import { useState } from "react";
import { parseDocument, checkCompliance, extractEntities, classifyContract } from "../../lib/api-client";

type AnalysisType = "compliance" | "ner" | "contract";
type FileResult = { name: string; status: "pending" | "running" | "done" | "error"; result?: string; error?: string };

export default function BatchAnalysisPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [analysisType, setAnalysisType] = useState<AnalysisType>("compliance");
  const [results, setResults] = useState<FileResult[]>([]);
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const addFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
  };

  const runAnalysis = async () => {
    if (files.length === 0 || running) return;
    setRunning(true);
    const initial: FileResult[] = files.map((f) => ({ name: f.name, status: "pending" }));
    setResults(initial);
    for (let i = 0; i < files.length; i++) {
      setResults((prev) => prev.map((r, j) => j === i ? { ...r, status: "running" } : r));
      try {
        let text: string;
        if (files[i].name.endsWith(".txt") || files[i].name.endsWith(".md")) { text = await files[i].text(); }
        else { const parsed = await parseDocument(files[i]); text = parsed.text; }
        let result: string;
        if (analysisType === "compliance") {
          const data = await checkCompliance(text);
          const s = data.summary || {};
          result = `Pass: ${s.passed || 0}, Warnings: ${s.warnings || 0}, Failed: ${s.failed || 0}`;
        } else if (analysisType === "ner") {
          const data = await extractEntities(text);
          const entities = data.entities || [];
          result = `${entities.length} entities found`;
        } else {
          const data = await classifyContract(text);
          const types = data.clause_types || data.predictions || [];
          result = types.map((t: any) => t.label || t.type).join(", ") || "No clauses detected";
        }
        setResults((prev) => prev.map((r, j) => j === i ? { ...r, status: "done", result } : r));
      } catch (err: any) {
        setResults((prev) => prev.map((r, j) => j === i ? { ...r, status: "error", error: err.message } : r));
      }
    }
    setRunning(false);
  };

  const toggle = (i: number) => setExpanded((prev) => { const next = new Set(prev); next.has(i) ? next.delete(i) : next.add(i); return next; });
  const statusColor = (s: string) => s === "done" ? "#16a34a" : s === "error" ? "#dc2626" : s === "running" ? "#d97706" : "#94a3b8";

  return (
    <div>
      <h2>Batch Document Analysis</h2>
      <p className="meta-line">Upload multiple documents and run compliance, NER, or contract analysis on all of them</p>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <input type="file" multiple accept=".pdf,.docx,.txt,.md" onChange={addFiles} style={{ font: "inherit" }} />
        <select value={analysisType} onChange={(e) => setAnalysisType(e.target.value as AnalysisType)} style={{ padding: "0.4rem", borderRadius: "0.5rem", border: "1px solid #94a3b8" }}>
          <option value="compliance">Compliance Check</option>
          <option value="ner">Entity Extraction</option>
          <option value="contract">Contract Classification</option>
        </select>
        <button type="button" onClick={runAnalysis} disabled={running || files.length === 0} style={{ padding: "0.4rem 0.8rem", borderRadius: "0.5rem", border: "none", background: "#0f172a", color: "#fff", cursor: running ? "not-allowed" : "pointer", font: "inherit" }}>{running ? "Processing..." : `Analyze ${files.length} file(s)`}</button>
      </div>
      {files.length > 0 && <p className="meta-line" style={{ marginBottom: "0.5rem" }}>{files.map((f) => f.name).join(", ")}</p>}
      {results.length > 0 && (
        <ul className="results-list">
          {results.map((r, i) => (
            <li key={i} className="result-card" onClick={() => toggle(i)} style={{ cursor: "pointer" }}>
              <div className="result-header">
                <span style={{ display: "inline-block", width: "0.65rem", height: "0.65rem", borderRadius: "999px", background: statusColor(r.status) }} />
                <strong>{r.name}</strong>
                <span style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: statusColor(r.status) }}>{r.status}</span>
              </div>
              {r.result && <p className="meta-line" style={{ margin: "0.2rem 0 0" }}>{r.result}</p>}
              {r.error && <p style={{ margin: "0.2rem 0 0", color: "#dc2626", fontSize: "0.85rem" }}>{r.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
