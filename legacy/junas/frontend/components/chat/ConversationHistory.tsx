"use client";
import { useState, useEffect } from "react";
import { listConversations, deleteConversation, type ConversationMeta } from "../../lib/conversation-store";

interface Props { isOpen: boolean; onSelect: (id: string) => void; onClose: () => void; }

function formatDate(ts: number): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(ts));
}

export default function ConversationHistory({ isOpen, onSelect, onClose }: Props) {
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  useEffect(() => { if (isOpen) setConversations(listConversations()); }, [isOpen]);
  if (!isOpen) return null;
  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteConversation(id);
    setConversations(listConversations());
  };
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 90, display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "10vh" }} onClick={onClose}>
      <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "0.75rem", boxShadow: "0 20px 60px rgba(0,0,0,0.15)", width: "420px", maxHeight: "500px", overflow: "hidden" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ padding: "0.75rem 1rem", borderBottom: "1px solid #e2e8f0", fontWeight: 700 }}>Chat History</div>
        <div style={{ maxHeight: "420px", overflowY: "auto" }}>
          {conversations.length === 0 && <div style={{ padding: "1.5rem", textAlign: "center", color: "#94a3b8" }}>No saved conversations</div>}
          {conversations.map((c) => (
            <div key={c.id} onClick={() => { onSelect(c.id); onClose(); }} style={{ padding: "0.5rem 1rem", cursor: "pointer", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center" }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#f8fafc"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: "0.85rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</div>
                <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{c.messageCount} messages &middot; {formatDate(c.updatedAt)}</div>
              </div>
              <button type="button" onClick={(e) => handleDelete(c.id, e)} style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", fontSize: "0.8rem", padding: "0.2rem" }} title="Delete">&times;</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
