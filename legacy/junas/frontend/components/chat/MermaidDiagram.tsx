"use client";
import { useState, useEffect, useRef } from "react";

export default function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, theme: "default", securityLevel: "strict", logLevel: "fatal" as any });
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        const { svg: rendered } = await mermaid.render(id, chart);
        if (!cancelled) { setSvg(rendered); setError(""); }
      } catch (err: any) {
        if (!cancelled) { setError(err?.message || "Diagram render error"); setSvg(""); }
        // clean up mermaid error elements
        document.querySelectorAll('[id^="dmermaid"]').forEach((el) => el.remove());
      }
    })();
    return () => { cancelled = true; };
  }, [chart]);

  if (error) {
    return (
      <div style={{ border: "1px solid #fca5a5", borderRadius: "0.5rem", padding: "0.5rem", background: "#fef2f2" }}>
        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#b91c1c" }}>Diagram Error</div>
        <pre style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.25rem", whiteSpace: "pre-wrap" }}>{error}</pre>
        <details style={{ marginTop: "0.25rem" }}><summary style={{ fontSize: "0.75rem", cursor: "pointer", color: "#64748b" }}>Source</summary><pre style={{ fontSize: "0.7rem", marginTop: "0.25rem" }}>{chart}</pre></details>
      </div>
    );
  }
  if (!svg) return <div style={{ padding: "0.5rem", color: "#64748b", fontSize: "0.8rem" }}>Rendering diagram...</div>;
  return <div ref={containerRef} dangerouslySetInnerHTML={{ __html: svg }} style={{ overflow: "auto", maxWidth: "100%" }} />;
}
