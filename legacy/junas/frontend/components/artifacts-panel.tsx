"use client";

interface Artifact {
  type: "code" | "table" | "text";
  language?: string;
  content: string;
  title: string;
}

function extractArtifacts(markdown: string): Artifact[] {
  const artifacts: Artifact[] = [];
  // extract fenced code blocks
  const codeRegex = /```(\w*)\n([\s\S]*?)```/g;
  let match;
  let codeIdx = 0;
  while ((match = codeRegex.exec(markdown)) !== null) {
    codeIdx++;
    const lang = match[1] || "text";
    artifacts.push({
      type: "code",
      language: lang,
      content: match[2].trim(),
      title: lang === "text" ? `Code Block ${codeIdx}` : `${lang.charAt(0).toUpperCase() + lang.slice(1)} (Block ${codeIdx})`,
    });
  }
  // extract markdown tables
  const tableRegex = /(\|.+\|[\r\n]+\|[-| :]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)/g;
  let tableIdx = 0;
  while ((match = tableRegex.exec(markdown)) !== null) {
    tableIdx++;
    artifacts.push({
      type: "table",
      content: match[1].trim(),
      title: `Table ${tableIdx}`,
    });
  }
  return artifacts;
}

interface Props { isOpen: boolean; onClose: () => void; content: string; }

export default function ArtifactsPanel({ isOpen, onClose, content }: Props) {
  if (!isOpen) return null;
  const artifacts = extractArtifacts(content);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="artifacts-overlay" onClick={onClose}>
      <div className="artifacts-panel" onClick={e => e.stopPropagation()}>
        <div className="artifacts-header">
          <span className="artifacts-header-title">Artifacts ({artifacts.length})</span>
          <button type="button" className="artifacts-close" onClick={onClose}>&times;</button>
        </div>
        <div className="artifacts-body">
          {artifacts.length === 0 && (
            <div style={{ textAlign: "center", padding: "2rem 1rem", color: "#A8A29E", fontSize: "0.85rem" }}>
              No extractable artifacts in this response.
              <p style={{ fontSize: "0.75rem", marginTop: "0.35rem" }}>Artifacts include code blocks, tables, and structured data.</p>
            </div>
          )}
          {artifacts.map((a, i) => (
            <div key={i} className="artifact-card">
              <div className="artifact-card-header">
                <span>{a.type === "code" ? `< / > ${a.title}` : a.title}</span>
                <button type="button" className="artifact-copy-btn" onClick={() => copyToClipboard(a.content)}>Copy</button>
              </div>
              <div className="artifact-card-body">
                <pre>{a.content}</pre>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export { extractArtifacts };
