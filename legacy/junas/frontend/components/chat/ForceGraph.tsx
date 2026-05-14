"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import type { NodeMap } from "../../lib/chat-tree";
import { getActivePath, findLeaves } from "../../lib/chat-tree";

interface ForceNode {
  id: string;
  role: string;
  label: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  isActive: boolean;
  isLeaf: boolean;
  isCurrent: boolean;
}

interface ForceEdge {
  source: string;
  target: string;
  isActive: boolean;
}

interface Props {
  nodeMap: NodeMap;
  currentLeafId: string;
  onSelectNode: (nodeId: string) => void;
}

const USER_COLOR = "#1C1917";
const USER_COLOR_INACTIVE = "#A8A29E";
const ASST_COLOR = "#57534E";
const ASST_COLOR_INACTIVE = "#D6D3D1";
const EDGE_ACTIVE = "#1C1917";
const EDGE_INACTIVE = "#D6D3D1";
const CURRENT_RING = "#1C1917";

export default function ForceGraph({ nodeMap, currentLeafId, onSelectNode }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<ForceNode[]>([]);
  const edgesRef = useRef<ForceEdge[]>([]);
  const alphaRef = useRef(1);
  const dragRef = useRef<{ nodeId: string | null }>({ nodeId: null });
  const panRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(1);
  const animRef = useRef(0);
  const pointerStartRef = useRef<{ x: number; y: number; time: number } | null>(null);
  const wasDragRef = useRef(false);
  const lastPanRef = useRef({ x: 0, y: 0 });
  const isPanningRef = useRef(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const sizeRef = useRef({ w: 0, h: 0 });

  // build graph data from nodeMap
  useEffect(() => {
    const activePath = getActivePath(nodeMap, currentLeafId);
    const leavesSet = new Set(findLeaves(nodeMap));
    const entries = Object.values(nodeMap);
    if (entries.length === 0) { nodesRef.current = []; edgesRef.current = []; return; }
    const existing = new Map(nodesRef.current.map(n => [n.id, n]));
    const nodes: ForceNode[] = entries.map((msg, i) => {
      const prev = existing.get(msg.id);
      const angle = (i / entries.length) * Math.PI * 2;
      const r = 120 + Math.random() * 80;
      return {
        id: msg.id,
        role: msg.role,
        label: msg.content.slice(0, 35).replace(/\n/g, " ") || "(empty)",
        x: prev ? prev.x : Math.cos(angle) * r,
        y: prev ? prev.y : Math.sin(angle) * r,
        vx: prev ? prev.vx : 0,
        vy: prev ? prev.vy : 0,
        radius: msg.role === "user" ? 10 : 7,
        isActive: activePath.has(msg.id),
        isLeaf: leavesSet.has(msg.id),
        isCurrent: msg.id === currentLeafId,
      };
    });
    const edges: ForceEdge[] = [];
    for (const msg of entries) {
      for (const childId of msg.childrenIds) {
        if (nodeMap[childId]) edges.push({ source: msg.id, target: childId, isActive: activePath.has(msg.id) && activePath.has(childId) });
      }
    }
    nodesRef.current = nodes;
    edgesRef.current = edges;
    alphaRef.current = 1; // reheat
  }, [nodeMap, currentLeafId]);

  // canvas resize
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      sizeRef.current = { w: width * dpr, h: height * dpr };
    });
    ro.observe(canvas.parentElement!);
    return () => ro.disconnect();
  }, []);

  // animation loop
  useEffect(() => {
    function tick() {
      simulate();
      render();
      animRef.current = requestAnimationFrame(tick);
    }
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  function simulate() {
    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    if (nodes.length < 2) return;
    const alpha = alphaRef.current;
    if (alpha < 0.001) return;
    const REPULSION = 4000;
    const SPRING_K = 0.008;
    const SPRING_LEN = 90;
    const CENTER_K = 0.008;
    const DAMPING = 0.82;
    // repulsion (O(n^2) — fine for typical conversation sizes)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[j].x - nodes[i].x;
        let dy = nodes[j].y - nodes[i].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (REPULSION * alpha) / (dist * dist);
        const fx = (dx / dist) * f;
        const fy = (dy / dist) * f;
        nodes[i].vx -= fx; nodes[i].vy -= fy;
        nodes[j].vx += fx; nodes[j].vy += fy;
      }
    }
    // spring
    const map = new Map(nodes.map(n => [n.id, n]));
    for (const e of edges) {
      const s = map.get(e.source);
      const t = map.get(e.target);
      if (!s || !t) continue;
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = SPRING_K * (dist - SPRING_LEN) * alpha;
      const fx = (dx / dist) * f;
      const fy = (dy / dist) * f;
      s.vx += fx; s.vy += fy;
      t.vx -= fx; t.vy -= fy;
    }
    // center
    for (const n of nodes) {
      n.vx -= n.x * CENTER_K * alpha;
      n.vy -= n.y * CENTER_K * alpha;
    }
    // integrate
    for (const n of nodes) {
      if (dragRef.current.nodeId === n.id) continue;
      n.vx *= DAMPING; n.vy *= DAMPING;
      n.x += n.vx; n.y += n.vy;
    }
    alphaRef.current *= 0.997;
  }

  function render() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { w, h } = sizeRef.current;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    const zoom = zoomRef.current;
    const pan = panRef.current;
    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(w / 2 + pan.x * dpr, h / 2 + pan.y * dpr);
    ctx.scale(zoom * dpr, zoom * dpr);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    // edges
    for (const e of edges) {
      const s = nodeMap.get(e.source);
      const t = nodeMap.get(e.target);
      if (!s || !t) continue;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.strokeStyle = e.isActive ? EDGE_ACTIVE : EDGE_INACTIVE;
      ctx.lineWidth = e.isActive ? 1.8 : 0.8;
      ctx.globalAlpha = e.isActive ? 0.7 : 0.25;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // nodes
    for (const n of nodes) {
      const r = n.isCurrent ? n.radius + 2 : n.radius;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = n.role === "user"
        ? (n.isActive ? USER_COLOR : USER_COLOR_INACTIVE)
        : (n.isActive ? ASST_COLOR : ASST_COLOR_INACTIVE);
      ctx.fill();
      if (n.isCurrent) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 4, 0, Math.PI * 2);
        ctx.strokeStyle = CURRENT_RING;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      if (n.id === hoveredId) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3, 0, Math.PI * 2);
        ctx.strokeStyle = USER_COLOR;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      // label
      if (zoom > 0.4) {
        const fontSize = Math.max(9, 11 / zoom);
        ctx.font = `${n.isCurrent ? 600 : 400} ${fontSize}px Manrope, system-ui, sans-serif`;
        ctx.fillStyle = n.isActive ? "#1C1917" : "#A8A29E";
        ctx.textBaseline = "middle";
        ctx.fillText(n.label, n.x + r + 6, n.y);
      }
    }
    ctx.restore();
  }

  // coordinate transform
  const toGraph = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const { w, h } = sizeRef.current;
    const dpr = window.devicePixelRatio || 1;
    const zoom = zoomRef.current;
    const pan = panRef.current;
    return {
      x: (clientX - rect.left - rect.width / 2 - pan.x) / zoom,
      y: (clientY - rect.top - rect.height / 2 - pan.y) / zoom,
    };
  }, []);

  const hitTest = useCallback((gx: number, gy: number): ForceNode | null => {
    for (let i = nodesRef.current.length - 1; i >= 0; i--) {
      const n = nodesRef.current[i];
      const dx = n.x - gx; const dy = n.y - gy;
      if (dx * dx + dy * dy < (n.radius + 6) ** 2) return n;
    }
    return null;
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    const g = toGraph(e.clientX, e.clientY);
    pointerStartRef.current = { x: e.clientX, y: e.clientY, time: Date.now() };
    wasDragRef.current = false;
    const node = hitTest(g.x, g.y);
    if (node) {
      dragRef.current = { nodeId: node.id };
      node.vx = 0; node.vy = 0;
      alphaRef.current = Math.max(alphaRef.current, 0.3); // reheat
      (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
    } else {
      isPanningRef.current = true;
      lastPanRef.current = { x: e.clientX, y: e.clientY };
      (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
    }
  }, [toGraph, hitTest]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (dragRef.current.nodeId) {
      const g = toGraph(e.clientX, e.clientY);
      const n = nodesRef.current.find(n => n.id === dragRef.current.nodeId);
      if (n) { n.x = g.x; n.y = g.y; n.vx = 0; n.vy = 0; }
      wasDragRef.current = true;
    } else if (isPanningRef.current) {
      panRef.current.x += e.clientX - lastPanRef.current.x;
      panRef.current.y += e.clientY - lastPanRef.current.y;
      lastPanRef.current = { x: e.clientX, y: e.clientY };
      wasDragRef.current = true;
    } else {
      const g = toGraph(e.clientX, e.clientY);
      const node = hitTest(g.x, g.y);
      setHoveredId(node?.id || null);
      const canvas = canvasRef.current;
      if (canvas) canvas.style.cursor = node ? "grab" : "default";
    }
  }, [toGraph, hitTest]);

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (dragRef.current.nodeId && !wasDragRef.current) {
      // click on node
      onSelectNode(dragRef.current.nodeId);
    }
    if (dragRef.current.nodeId) alphaRef.current = Math.max(alphaRef.current, 0.3);
    dragRef.current = { nodeId: null };
    isPanningRef.current = false;
  }, [onSelectNode]);

  const onWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.92 : 1.08;
    zoomRef.current = Math.max(0.1, Math.min(6, zoomRef.current * factor));
  }, []);

  const entries = Object.values(nodeMap);
  if (entries.length === 0) {
    return <p className="meta-line" style={{ padding: "1.5rem", textAlign: "center" }}>Start chatting to visualize the conversation graph.</p>;
  }

  const hoveredNode = hoveredId ? nodeMap[hoveredId] : null;

  return (
    <div style={{ width: "100%", height: "100%", position: "relative", minHeight: "400px" }}>
      <canvas ref={canvasRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
        onWheel={onWheel} style={{ width: "100%", height: "100%", display: "block", touchAction: "none" }} />
      {/* hover tooltip */}
      {hoveredNode && (
        <div style={{
          position: "absolute", bottom: "0.75rem", left: "0.75rem",
          background: "#FFFFFF", border: "1px solid #E7E5E4", borderRadius: "0.5rem",
          padding: "0.5rem 0.75rem", maxWidth: "320px", fontSize: "0.78rem",
          boxShadow: "0 4px 16px rgba(0,0,0,0.08)", pointerEvents: "none",
        }}>
          <div style={{ fontWeight: 700, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "#A8A29E", marginBottom: "0.2rem" }}>
            {hoveredNode.role === "user" ? "You" : "Junas"}
          </div>
          <div style={{ color: "#1C1917", lineHeight: 1.4 }}>
            {hoveredNode.content.slice(0, 300) || "(empty)"}
            {hoveredNode.content.length > 300 && "..."}
          </div>
        </div>
      )}
      {/* controls hint */}
      <div style={{
        position: "absolute", top: "0.5rem", right: "0.75rem",
        fontSize: "0.68rem", color: "#A8A29E", pointerEvents: "none",
      }}>
        drag nodes · scroll to zoom · click to navigate
      </div>
    </div>
  );
}
