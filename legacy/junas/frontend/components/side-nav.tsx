"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { listConversations, deleteConversation, type ConversationMeta } from "../lib/conversation-store";
import ThemeToggle from "./theme-toggle";
import NotificationsPanel, { useUnreadCount } from "./notifications-panel";

const TOOL_LINKS = [
  { href: "/glossary", label: "Glossary" },
  { href: "/statutes", label: "Statutes" },
  { href: "/search", label: "Case Search" },
  { href: "/research", label: "Research" },
  { href: "/legal-sources", label: "Legal Sources" },
  { href: "/contracts", label: "Contracts" },
  { href: "/ner", label: "NER" },
  { href: "/compliance", label: "Compliance" },
  { href: "/batch-analysis", label: "Batch Analysis" },
  { href: "/clauses", label: "Clauses" },
  { href: "/templates", label: "Templates" },
  { href: "/predictions", label: "Predictions" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/rome-statute", label: "Rome Statute" },
  { href: "/compare-jurisdictions", label: "Compare" },
  { href: "/documents", label: "Documents" },
];

function formatDate(ts: number): string {
  const now = Date.now();
  const diff = now - ts;
  if (diff < 86400000) return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(ts));
  if (diff < 604800000) return new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(new Date(ts));
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(ts));
}

export default function SideNav() {
  const pathname = usePathname();
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeConvId, setActiveConvId] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const unreadCount = useUnreadCount();

  useEffect(() => {
    setConversations(listConversations());
    const refresh = () => setConversations(listConversations());
    const onActive = (e: Event) => setActiveConvId((e as CustomEvent).detail?.id || "");
    window.addEventListener("junas:conversations-updated", refresh);
    window.addEventListener("junas:active-conversation", onActive);
    return () => {
      window.removeEventListener("junas:conversations-updated", refresh);
      window.removeEventListener("junas:active-conversation", onActive);
    };
  }, []);

  // auto-expand tools section on tool pages
  useEffect(() => {
    if (TOOL_LINKS.some(t => pathname.startsWith(t.href))) setToolsOpen(true);
  }, [pathname]);

  const handleNewChat = () => {
    if (pathname === "/") {
      window.dispatchEvent(new CustomEvent("junas:new-chat"));
    } else {
      window.location.href = "/";
    }
    setActiveConvId("");
    setMobileOpen(false);
  };

  const handleLoadConversation = (id: string) => {
    if (pathname === "/") {
      window.dispatchEvent(new CustomEvent("junas:load-conversation", { detail: { id } }));
    } else {
      window.location.href = `/?c=${id}`;
    }
    setActiveConvId(id);
    setMobileOpen(false);
  };

  const handleDeleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteConversation(id);
    setConversations(listConversations());
    if (activeConvId === id) {
      window.dispatchEvent(new CustomEvent("junas:new-chat"));
      setActiveConvId("");
    }
  };

  return (
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-header">
        <Link href="/" className="sidebar-brand" onClick={() => setMobileOpen(false)}>Junas</Link>
        <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
          <button type="button" className="sidebar-new-chat" onClick={handleNewChat}>+ New</button>
          <button type="button" className="sidebar-toggle" onClick={() => setMobileOpen(v => !v)} aria-label="Toggle navigation">
            {mobileOpen ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      <div className="sidebar-section-title">Recent</div>
      <div className="sidebar-conversations">
        {conversations.length === 0 && (
          <div style={{ padding: "0.75rem 0.6rem", color: "#A8A29E", fontSize: "0.78rem" }}>No conversations yet</div>
        )}
        {conversations.slice(0, 50).map(c => (
          <div key={c.id} className={`sidebar-conv-item ${activeConvId === c.id ? "active" : ""}`} onClick={() => handleLoadConversation(c.id)}>
            <span className="sidebar-conv-title">{c.title}</span>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="sidebar-conv-meta">{c.messageCount} msgs · {formatDate(c.updatedAt)}</span>
              <button type="button" className="sidebar-conv-delete" onClick={(e) => handleDeleteConversation(c.id, e)} title="Delete">&times;</button>
            </div>
          </div>
        ))}
      </div>

      <div className="sidebar-tools">
        <button type="button" className="sidebar-tools-toggle" onClick={() => setToolsOpen(v => !v)}>
          <span>Tools</span>
          <span style={{ fontSize: "0.6rem", transition: "transform 0.2s", transform: toolsOpen ? "rotate(180deg)" : "rotate(0)", display: "inline-block" }}>&#9660;</span>
        </button>
        {toolsOpen && (
          <nav className="sidebar-tools-nav">
            {TOOL_LINKS.map(t => (
              <Link key={t.href} href={t.href}
                className={`sidebar-tool-link ${pathname === t.href || pathname.startsWith(`${t.href}/`) ? "active" : ""}`}
                onClick={() => setMobileOpen(false)}>
                {t.label}
              </Link>
            ))}
          </nav>
        )}
      </div>

      <div className="sidebar-footer">
        <Link href="/settings" className="sidebar-settings-link" onClick={() => setMobileOpen(false)}>Settings</Link>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <button type="button" className="sidebar-notif-btn" onClick={() => setNotifOpen(true)} title="Notifications">
            <span>Logs</span>
            {unreadCount > 0 && <span className="notif-badge">{unreadCount > 99 ? "99+" : unreadCount}</span>}
          </button>
          <ThemeToggle />
        </div>
      </div>
      <NotificationsPanel isOpen={notifOpen} onClose={() => setNotifOpen(false)} />
    </aside>
  );
}
