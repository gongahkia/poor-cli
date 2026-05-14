"use client";

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4); // rough 4 chars/token estimate
}

interface Props {
  content: string;
  isStreaming?: boolean;
  provider?: string;
  responseTimeMs?: number;
}

export default function TokenCounter({ content, isStreaming, provider, responseTimeMs }: Props) {
  const tokens = estimateTokens(content);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.7rem", color: "#94a3b8", fontFamily: "monospace" }}>
      {isStreaming && <span style={{ animation: "pulse 1s infinite" }}>...</span>}
      <span>{tokens.toLocaleString()} tok</span>
      {provider && <><span>&middot;</span><span>{provider}</span></>}
      {responseTimeMs != null && <><span>&middot;</span><span>{responseTimeMs < 1000 ? `${responseTimeMs}ms` : `${(responseTimeMs / 1000).toFixed(1)}s`}</span></>}
    </div>
  );
}
