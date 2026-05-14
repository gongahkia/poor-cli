"use client";
import { memo, lazy, Suspense, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MermaidDiagram = lazy(() => import("./MermaidDiagram"));
const DIAGRAM_LANGS = new Set(["mermaid", "diagram", "plantuml", "d2", "graphviz", "dot"]);

function CodeBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  const text = String(children).replace(/\n$/, "");
  const langMatch = /language-(\w+)/.exec(className || "");
  const lang = langMatch?.[1] ?? "";
  const [copied, setCopied] = useState(false);
  if (DIAGRAM_LANGS.has(lang)) {
    return <Suspense fallback={<pre style={{ padding: "0.5rem", background: "#f1f5f9", borderRadius: "0.5rem" }}>{text}</pre>}><MermaidDiagram chart={text} /></Suspense>;
  }
  const copy = () => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); };
  return (
    <div style={{ position: "relative", marginBottom: "0.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#1e293b", color: "#94a3b8", padding: "0.25rem 0.5rem", borderRadius: "0.5rem 0.5rem 0 0", fontSize: "0.7rem", fontFamily: "monospace" }}>
        <span>{lang || "code"}</span>
        <button type="button" onClick={copy} style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "0.7rem" }}>{copied ? "Copied!" : "Copy"}</button>
      </div>
      <pre style={{ margin: 0, padding: "0.6rem", background: "#0f172a", color: "#e2e8f0", borderRadius: "0 0 0.5rem 0.5rem", overflow: "auto", fontSize: "0.8rem", lineHeight: 1.5 }}><code>{text}</code></pre>
    </div>
  );
}

function MarkdownRendererInner({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const isBlock = /language-/.test(className || "") || String(children).includes("\n");
          if (isBlock) return <CodeBlock className={className}>{children}</CodeBlock>;
          return <code style={{ background: "#f1f5f9", padding: "0.1rem 0.3rem", borderRadius: "0.25rem", fontSize: "0.85em" }} {...props}>{children}</code>;
        },
        table({ children }) { return <div style={{ overflowX: "auto", marginBottom: "0.5rem" }}><table style={{ borderCollapse: "collapse", width: "100%" }}>{children}</table></div>; },
        th({ children }) { return <th style={{ border: "1px solid #cbd5e1", padding: "0.4rem 0.5rem", textAlign: "left", background: "#f1f5f9", fontWeight: 600 }}>{children}</th>; },
        td({ children }) { return <td style={{ border: "1px solid #cbd5e1", padding: "0.4rem 0.5rem", verticalAlign: "top" }}>{children}</td>; },
      }}
    >{content}</ReactMarkdown>
  );
}

const MarkdownRenderer = memo(MarkdownRendererInner);
export default MarkdownRenderer;
