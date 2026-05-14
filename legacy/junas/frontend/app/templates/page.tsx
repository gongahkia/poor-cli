"use client";
import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Variable = { name: string; label: string; placeholder: string; type: string };
type Template = { id: string; title: string; category: string; jurisdiction: string; description: string; variables: Variable[]; content: string };

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Template | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [rendered, setRendered] = useState("");

  useEffect(() => {
    fetch(`${API}/api/v1/templates`).then((r) => r.json()).then(setTemplates).catch(() => {});
  }, []);

  const selectTemplate = (t: Template) => {
    setSelected(t);
    setValues({});
    setRendered("");
  };

  const renderDoc = async () => {
    if (!selected) return;
    const resp = await fetch(`${API}/api/v1/templates/${selected.id}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    const data = await resp.json();
    setRendered(data.rendered || "");
  };

  return (
    <div>
      <h2>Template Library</h2>
      <p className="meta-line">Legal document templates with variable substitution</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1rem" }}>
        <ul className="results-list">
          {templates.map((t) => (
            <li key={t.id} className="result-card" style={{ cursor: "pointer", borderColor: selected?.id === t.id ? "#3b82f6" : undefined }} onClick={() => selectTemplate(t)}>
              <strong>{t.title}</strong>
              <div style={{ display: "flex", gap: "0.3rem", marginTop: "0.2rem" }}>
                <span className="badge muted">{t.category}</span>
                <span className="badge">{t.jurisdiction}</span>
              </div>
              <p className="meta-line" style={{ margin: "0.2rem 0 0" }}>{t.description}</p>
            </li>
          ))}
        </ul>
        <div>
          {selected ? (
            <div className="result-card">
              <h3 style={{ margin: "0 0 0.5rem" }}>{selected.title}</h3>
              <div style={{ display: "grid", gap: "0.4rem", marginBottom: "0.75rem" }}>
                {selected.variables.map((v) => (
                  <div key={v.name}>
                    <label style={{ fontSize: "0.8rem", fontWeight: 600 }}>{v.label}</label>
                    <input value={values[v.name] || ""} onChange={(e) => setValues({ ...values, [v.name]: e.target.value })} placeholder={v.placeholder} type={v.type === "date" ? "date" : v.type === "number" ? "number" : "text"} style={{ width: "100%", padding: "0.4rem", borderRadius: "0.5rem", border: "1px solid #94a3b8", font: "inherit" }} />
                  </div>
                ))}
              </div>
              <button type="button" onClick={renderDoc} style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", background: "#0f172a", color: "#fff", cursor: "pointer", font: "inherit", marginBottom: "0.75rem" }}>Render Document</button>
              {rendered && <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, borderTop: "1px solid #e2e8f0", paddingTop: "0.75rem" }}>{rendered}</div>}
            </div>
          ) : (
            <div className="result-card"><p className="meta-line">Select a template to fill and render</p></div>
          )}
        </div>
      </div>
    </div>
  );
}
