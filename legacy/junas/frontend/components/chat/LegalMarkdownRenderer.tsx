"use client";
import { memo, lazy, Suspense } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

const MermaidDiagram = lazy(() => import("./MermaidDiagram"));
const DIAGRAM_LANGS = new Set(["mermaid", "diagram", "plantuml", "d2", "graphviz", "dot"]);

// citation patterns for auto-linking
const CITATION_PATTERNS: { regex: RegExp; href: (m: RegExpMatchArray) => string }[] = [
  { regex: /ORS\s+(\d{1,4}[A-Z]?\.\d{3,4})/g, href: (m) => `/statutes/section/${m[1]}` },
  { regex: /(?:Rome\s+Statute|RS)\s+[Aa]rt(?:icle)?\.?\s*(\d+)/g, href: (m) => `/rome-statute/article/${m[1]}` },
  { regex: /\[(\d{4})\]\s+(?:SGCA|SGHC)\s+\d+/g, href: (m) => `/legal-sources?query=${encodeURIComponent(m[0])}` },
  { regex: /\[(\d{4})\]\s+\d+\s+SLR(?:\(R\))?\s+\d+/g, href: (m) => `/legal-sources?query=${encodeURIComponent(m[0])}` },
  { regex: /\b([A-Z][A-Za-z'/-]+(?:\s+[A-Z][A-Za-z'/-]+)*\s+Act)\s*\(Cap\.\s*\d+/g, href: (m) => `/legal-sources?query=${encodeURIComponent(m[1])}` },
];

function linkifyCitations(text: string): (string | JSX.Element)[] {
  const parts: (string | JSX.Element)[] = [];
  let lastIndex = 0;
  const allMatches: { start: number; end: number; text: string; href: string }[] = [];
  for (const { regex, href } of CITATION_PATTERNS) {
    regex.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = regex.exec(text)) !== null) {
      allMatches.push({ start: m.index, end: m.index + m[0].length, text: m[0], href: href(m) });
    }
  }
  allMatches.sort((a, b) => a.start - b.start);
  // dedupe overlapping
  const deduped: typeof allMatches = [];
  for (const m of allMatches) {
    if (deduped.length === 0 || m.start >= deduped[deduped.length - 1].end) deduped.push(m);
  }
  for (const m of deduped) {
    if (m.start > lastIndex) parts.push(text.slice(lastIndex, m.start));
    parts.push(<Link key={m.start} href={m.href} style={{ color: "#1d4ed8", textDecoration: "underline", textUnderlineOffset: "2px" }}>{m.text}</Link>);
    lastIndex = m.end;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

function CodeBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  const text = String(children).replace(/\n$/, "");
  const langMatch = /language-(\w+)/.exec(className || "");
  const lang = langMatch?.[1] ?? "";
  if (DIAGRAM_LANGS.has(lang)) {
    return <Suspense fallback={<pre style={{ padding: "0.5rem", background: "#f1f5f9", borderRadius: "0.5rem" }}>{text}</pre>}><MermaidDiagram chart={text} /></Suspense>;
  }
  return (
    <div style={{ position: "relative", marginBottom: "0.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", background: "#1e293b", color: "#94a3b8", padding: "0.25rem 0.5rem", borderRadius: "0.5rem 0.5rem 0 0", fontSize: "0.7rem", fontFamily: "monospace" }}><span>{lang || "code"}</span></div>
      <pre style={{ margin: 0, padding: "0.6rem", background: "#0f172a", color: "#e2e8f0", borderRadius: "0 0 0.5rem 0.5rem", overflow: "auto", fontSize: "0.8rem", lineHeight: 1.5 }}><code>{text}</code></pre>
    </div>
  );
}

function LegalMarkdownRendererInner({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const isBlock = /language-/.test(className || "") || String(children).includes("\n");
          if (isBlock) return <CodeBlock className={className}>{children}</CodeBlock>;
          return <code style={{ background: "#f1f5f9", padding: "0.1rem 0.3rem", borderRadius: "0.25rem", fontSize: "0.85em" }} {...props}>{children}</code>;
        },
        p({ children }) {
          // process text children for citation linking
          const processed = Array.isArray(children) ? children.map((child, i) =>
            typeof child === "string" ? <span key={i}>{linkifyCitations(child)}</span> : child
          ) : typeof children === "string" ? linkifyCitations(children) : children;
          return <p>{processed}</p>;
        },
        table({ children }) { return <div style={{ overflowX: "auto", marginBottom: "0.5rem" }}><table style={{ borderCollapse: "collapse", width: "100%" }}>{children}</table></div>; },
        th({ children }) { return <th style={{ border: "1px solid #cbd5e1", padding: "0.4rem 0.5rem", textAlign: "left", background: "#f1f5f9", fontWeight: 600 }}>{children}</th>; },
        td({ children }) { return <td style={{ border: "1px solid #cbd5e1", padding: "0.4rem 0.5rem", verticalAlign: "top" }}>{children}</td>; },
      }}
    >{content}</ReactMarkdown>
  );
}

export default memo(LegalMarkdownRendererInner);
