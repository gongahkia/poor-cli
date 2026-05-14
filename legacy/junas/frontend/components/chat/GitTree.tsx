"use client";
import { useMemo } from "react";
import type { NodeMap, GraphNode, GraphEdge } from "../../lib/chat-tree";
import { computeGitGraphLayout } from "../../lib/chat-tree";

const NODE_RADIUS = 6;
const ROW_HEIGHT = 52;
const LANE_WIDTH = 24;
const GRAPH_LEFT = 16;
const LABEL_LEFT = 8; // gap after graph area

const BRANCH_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
];

function laneColor(lane: number): string {
  return BRANCH_COLORS[lane % BRANCH_COLORS.length];
}

interface GitTreeProps {
  nodeMap: NodeMap;
  currentLeafId: string;
  onSelectNode: (nodeId: string) => void;
}

export default function GitTree({ nodeMap, currentLeafId, onSelectNode }: GitTreeProps) {
  const layout = useMemo(() => computeGitGraphLayout(nodeMap, currentLeafId), [nodeMap, currentLeafId]);
  if (layout.nodes.length === 0) {
    return <p style={{ color: "#64748b", fontSize: "0.875rem" }}>No conversation tree yet. Start chatting to build branches.</p>;
  }
  const graphWidth = GRAPH_LEFT + (layout.maxLane + 1) * LANE_WIDTH + 12;
  const totalHeight = (layout.maxRow + 1) * ROW_HEIGHT + 16;
  const svgWidth = graphWidth;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, overflowY: "auto", maxHeight: "75vh" }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", padding: "0.25rem 0" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><line x1="12" y1="9" x2="6" y2="15"/><line x1="12" y1="9" x2="18" y2="15"/></svg>
        <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>Conversation Graph</span>
        <span style={{ fontSize: "0.75rem", color: "#64748b" }}>
          {layout.nodes.length} messages &middot; {layout.maxLane + 1} branch{layout.maxLane > 0 ? "es" : ""}
        </span>
      </div>
      {/* graph rows */}
      <div style={{ position: "relative" }}>
        {/* SVG layer: edges and nodes */}
        <svg width={svgWidth} height={totalHeight} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}>
          {/* edges */}
          {layout.edges.map((e, i) => {
            const x1 = GRAPH_LEFT + e.fromLane * LANE_WIDTH;
            const y1 = e.fromRow * ROW_HEIGHT + ROW_HEIGHT / 2;
            const x2 = GRAPH_LEFT + e.toLane * LANE_WIDTH;
            const y2 = e.toRow * ROW_HEIGHT + ROW_HEIGHT / 2;
            const color = laneColor(e.toLane);
            if (e.fromLane === e.toLane) {
              return <line key={`e${i}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={e.isActive ? 2.5 : 1.5} opacity={e.isActive ? 1 : 0.45} />;
            }
            // curved edge for branch/merge
            const midY = y1 + (y2 - y1) * 0.35;
            const d = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
            return <path key={`e${i}`} d={d} fill="none" stroke={color} strokeWidth={e.isActive ? 2.5 : 1.5} opacity={e.isActive ? 1 : 0.45} />;
          })}
          {/* nodes */}
          {layout.nodes.map((n) => {
            const cx = GRAPH_LEFT + n.lane * LANE_WIDTH;
            const cy = n.row * ROW_HEIGHT + ROW_HEIGHT / 2;
            const color = laneColor(n.lane);
            const r = n.isLeaf ? NODE_RADIUS + 2 : NODE_RADIUS;
            return (
              <g key={`n${n.id}`}>
                <circle cx={cx} cy={cy} r={r} fill={n.isActive ? color : "#94a3b8"} stroke={n.id === currentLeafId ? "#fff" : "none"} strokeWidth={n.id === currentLeafId ? 2.5 : 0} opacity={n.isActive ? 1 : 0.55} />
                {n.id === currentLeafId && <circle cx={cx} cy={cy} r={r + 4} fill="none" stroke={color} strokeWidth={1.5} strokeDasharray="3 2" />}
              </g>
            );
          })}
        </svg>
        {/* Label rows (clickable) */}
        {layout.nodes.map((n) => {
          const top = n.row * ROW_HEIGHT;
          const leftOffset = graphWidth + LABEL_LEFT;
          const isCurrentLeaf = n.id === currentLeafId;
          return (
            <div
              key={n.id}
              onClick={() => onSelectNode(n.id)}
              style={{
                position: "relative", height: ROW_HEIGHT, display: "flex", alignItems: "center",
                paddingLeft: leftOffset, cursor: "pointer", borderRadius: "0.375rem",
                background: isCurrentLeaf ? "rgba(59,130,246,0.08)" : n.isActive ? "rgba(59,130,246,0.03)" : "transparent",
                borderLeft: isCurrentLeaf ? `3px solid ${laneColor(n.lane)}` : "3px solid transparent",
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "rgba(59,130,246,0.06)"; }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = isCurrentLeaf ? "rgba(59,130,246,0.08)" : n.isActive ? "rgba(59,130,246,0.03)" : "transparent";
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", minWidth: 0, flex: 1 }}>
                {/* role badge */}
                <span style={{
                  fontSize: "0.65rem", fontWeight: 700, fontFamily: "monospace", textTransform: "uppercase",
                  padding: "0.1rem 0.3rem", borderRadius: "0.25rem", flexShrink: 0,
                  background: n.role === "user" ? "#dbeafe" : "#d1fae5",
                  color: n.role === "user" ? "#1d4ed8" : "#047857",
                }}>{n.role === "user" ? "YOU" : "AI"}</span>
                {/* message preview */}
                <span style={{
                  fontSize: "0.8rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  color: n.isActive ? "#0f172a" : "#64748b",
                  fontWeight: isCurrentLeaf ? 600 : 400,
                }}>{n.label || "(empty)"}</span>
                {/* leaf / HEAD indicator */}
                {isCurrentLeaf && (
                  <span style={{
                    fontSize: "0.6rem", fontWeight: 700, fontFamily: "monospace", padding: "0.05rem 0.35rem",
                    borderRadius: "0.25rem", background: laneColor(n.lane), color: "#fff", flexShrink: 0,
                  }}>HEAD</span>
                )}
                {n.isLeaf && !isCurrentLeaf && (
                  <span style={{
                    fontSize: "0.6rem", fontFamily: "monospace", padding: "0.05rem 0.3rem",
                    borderRadius: "0.25rem", border: `1px solid ${laneColor(n.lane)}`,
                    color: laneColor(n.lane), flexShrink: 0,
                  }}>leaf</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
