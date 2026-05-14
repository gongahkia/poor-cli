"use client";
import { useState, useRef, useEffect, useCallback, lazy, Suspense } from "react";
import type { NodeMap, TreeMessage, MessageRole } from "../lib/chat-tree";
import { createId, getLinearHistory, getBranchSiblings, addChild, findLeaves } from "../lib/chat-tree";
import { parseDocument } from "../lib/api-client";
import { handleCommand } from "../lib/commands/command-handler";
import { saveConversation, loadConversation, generateConversationId, listConversations } from "../lib/conversation-store";
import { useKeyboardShortcuts } from "../lib/use-keyboard-shortcuts";
import TokenCounter from "../components/chat/TokenCounter";
import CommandSuggestions, { COMMANDS } from "../components/chat/CommandSuggestions";
import { addNotification } from "../lib/notification-store";
import ProviderSelector from "../components/provider-selector";
import ArtifactsPanel, { extractArtifacts } from "../components/artifacts-panel";

const LegalMarkdownRenderer = lazy(() => import("../components/chat/LegalMarkdownRenderer"));
const ForceGraph = lazy(() => import("../components/chat/ForceGraph"));
const CommandPalette = lazy(() => import("../components/chat/CommandPalette"));

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Tab = "chat" | "tree";

export default function HomePage() {
  // tree state
  const [nodeMap, setNodeMap] = useState<NodeMap>({});
  const [currentLeafId, setCurrentLeafId] = useState("");
  const [conversationId, setConversationId] = useState("");
  // UI
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState("claude");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  // commands
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdQuery, setCmdQuery] = useState("");
  const [cmdIndex, setCmdIndex] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // file upload
  const [pendingFile, setPendingFile] = useState<{ name: string; text: string } | null>(null);
  // artifacts
  const [artifactsContent, setArtifactsContent] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  // refs
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const startTimeRef = useRef(0);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const messages = currentLeafId ? getLinearHistory(nodeMap, currentLeafId) : [];
  const isEmpty = messages.length === 0 && !streaming;
  const leaves = findLeaves(nodeMap);

  // auto-scroll
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages.length, streaming]);
  // load API key
  useEffect(() => { setApiKey(localStorage.getItem(`junas_apikey_${provider}`) || ""); }, [provider]);
  // load jurisdiction system prompt
  useEffect(() => {
    const stored = localStorage.getItem("junas_jurisdiction_prompt");
    if (stored && !systemPrompt) setSystemPrompt(stored);
  }, []);

  // persistence
  useEffect(() => {
    if (!conversationId || Object.keys(nodeMap).length === 0) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveConversation(conversationId, nodeMap, currentLeafId);
      window.dispatchEvent(new CustomEvent("junas:conversations-updated"));
    }, 500);
  }, [nodeMap, currentLeafId, conversationId]);

  // keyboard shortcuts
  useKeyboardShortcuts({
    onCommandPalette: () => setPaletteOpen(true),
    onNewChat: () => newChat(),
  });

  // sidebar events
  useEffect(() => {
    const handleLoad = (e: Event) => {
      const id = (e as CustomEvent).detail?.id;
      if (id) loadFromHistory(id);
    };
    const handleNew = () => newChat();
    window.addEventListener("junas:load-conversation", handleLoad);
    window.addEventListener("junas:new-chat", handleNew);
    return () => {
      window.removeEventListener("junas:load-conversation", handleLoad);
      window.removeEventListener("junas:new-chat", handleNew);
    };
  }, []);

  // load from URL param on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const convId = params.get("c");
    if (convId) {
      loadFromHistory(convId);
      window.history.replaceState({}, "", "/"); // clean URL
    }
  }, []);

  // --- core logic ---
  const sendMessage = async (overrideContent?: string) => {
    const rawText = (overrideContent ?? input).trim();
    if (!rawText || streaming) return;
    if (!overrideContent) setInput("");
    let text = rawText;
    if (pendingFile && !overrideContent) {
      text = `[Document: ${pendingFile.name}]\n\n${pendingFile.text}\n\n---\n\n${rawText}`;
      setPendingFile(null);
    }
    let cid = conversationId;
    if (!cid) { cid = generateConversationId(); setConversationId(cid); }
    let map = nodeMap;
    let parentId = currentLeafId;
    if (!parentId) {
      const root: TreeMessage = { id: createId(), role: "user", content: text, childrenIds: [], timestamp: Date.now() };
      map = { [root.id]: root };
      parentId = root.id;
    } else {
      const userMsg: TreeMessage = { id: createId(), role: "user", content: text, parentId, childrenIds: [], timestamp: Date.now() };
      map = addChild(map, parentId, userMsg);
      parentId = userMsg.id;
    }
    setNodeMap(map);
    setCurrentLeafId(parentId);
    notifyActiveConversation(cid);
    // commands
    const cmdResult = await handleCommand(text);
    if (cmdResult.isCommand) {
      const asstId = createId();
      const asst: TreeMessage = { id: asstId, role: "assistant", content: cmdResult.response || "", parentId, childrenIds: [], timestamp: Date.now() };
      const newMap = addChild(map, parentId, asst);
      setNodeMap(newMap);
      setCurrentLeafId(asstId);
      return;
    }
    // stream AI response using shared function
    streamResponse(map, parentId);
  };

  const stopGeneration = () => { abortRef.current?.abort(); };
  const newChat = () => { setNodeMap({}); setCurrentLeafId(""); setConversationId(""); setActiveTab("chat"); };
  const notifyActiveConversation = (id: string) => { window.dispatchEvent(new CustomEvent("junas:active-conversation", { detail: { id } })); };

  const startEdit = (msgId: string) => { const msg = nodeMap[msgId]; if (msg?.role === "user") { setEditingId(msgId); setEditContent(msg.content); } };
  const saveEdit = () => {
    if (!editingId || !nodeMap[editingId]?.parentId) return;
    const parentOfEdited = nodeMap[editingId].parentId!;
    const edited: TreeMessage = { id: createId(), role: "user", content: editContent.trim(), parentId: parentOfEdited, childrenIds: [], timestamp: Date.now() };
    const newMap = addChild(nodeMap, parentOfEdited, edited);
    setEditingId(null); setEditContent("");
    // stream directly from the branch point — don't go through sendMessage
    streamResponse(newMap, edited.id);
  };

  // core streaming function — takes explicit map and parentId to avoid stale closures
  const streamResponse = async (map: NodeMap, userNodeId: string) => {
    let cid = conversationId;
    if (!cid) { cid = generateConversationId(); setConversationId(cid); }
    const asstId = createId();
    const asstMsg: TreeMessage = { id: asstId, role: "assistant", content: "", parentId: userNodeId, childrenIds: [], timestamp: Date.now() };
    map = addChild(map, userNodeId, asstMsg);
    setNodeMap(map);
    setCurrentLeafId(asstId);
    notifyActiveConversation(cid);
    setStreaming(true);
    startTimeRef.current = Date.now();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const history = getLinearHistory(map, asstId).slice(0, -1);
      const resp = await fetch(`${API_BASE}/api/v1/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider, model: model || undefined,
          messages: history.map(m => ({ role: m.role, content: m.content })),
          api_key: apiKey || localStorage.getItem(`junas_apikey_${provider}`) || "",
          system_prompt: systemPrompt || undefined, max_tokens: 4096,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = "", accumulated = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.error) throw new Error(ev.error);
            if (ev.delta) {
              accumulated += ev.delta;
              setNodeMap(prev => ({ ...prev, [asstId]: { ...prev[asstId], content: accumulated, responseTimeMs: Date.now() - startTimeRef.current } }));
            }
          } catch {}
        }
      }
      setNodeMap(prev => ({ ...prev, [asstId]: { ...prev[asstId], content: accumulated, responseTimeMs: Date.now() - startTimeRef.current } }));
    } catch (err: any) {
      if (err.name !== "AbortError") {
        addNotification("error", "Chat Error", err.message || "Failed to get response");
        setNodeMap(prev => {
          const updated = { ...prev };
          delete updated[asstId];
          if (updated[userNodeId]) updated[userNodeId] = { ...updated[userNodeId], childrenIds: updated[userNodeId].childrenIds.filter(c => c !== asstId) };
          return updated;
        });
        setCurrentLeafId(userNodeId);
      }
    } finally { setStreaming(false); abortRef.current = null; }
  };

  const switchBranch = (msgId: string, dir: "prev" | "next") => {
    const sibs = getBranchSiblings(nodeMap, msgId);
    const idx = sibs.indexOf(msgId) + (dir === "prev" ? -1 : 1);
    if (idx < 0 || idx >= sibs.length) return;
    let leaf = sibs[idx];
    while (nodeMap[leaf]?.childrenIds.length > 0) leaf = nodeMap[leaf].childrenIds[0];
    setCurrentLeafId(leaf);
  };

  const onSelectNode = (nodeId: string) => {
    let leaf = nodeId;
    while (nodeMap[leaf]?.childrenIds.length > 0) leaf = nodeMap[leaf].childrenIds[0];
    setCurrentLeafId(leaf); setActiveTab("chat");
  };

  const loadFromHistory = (id: string) => {
    const conv = loadConversation(id);
    if (!conv) return;
    setNodeMap(conv.nodeMap); setCurrentLeafId(conv.currentLeafId); setConversationId(id); setActiveTab("chat");
    notifyActiveConversation(id);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      if (file.name.endsWith(".txt") || file.name.endsWith(".md")) {
        const text = await file.text();
        setPendingFile({ name: file.name, text });
      } else {
        const result = await parseDocument(file);
        setPendingFile({ name: result.filename || file.name, text: result.text });
      }
    } catch (err: any) { addNotification("error", "File Error", `Failed to parse ${file.name}: ${err.message}`); }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const exportChat = (format: "md" | "txt") => {
    const history = currentLeafId ? getLinearHistory(nodeMap, currentLeafId) : [];
    if (history.length === 0) return;
    const content = format === "md"
      ? `# Chat Export\n\n${history.map(m => `## ${m.role === "user" ? "You" : "Junas"}\n\n${m.content}\n`).join("\n---\n\n")}`
      : history.map(m => `[${m.role}]\n${m.content}`).join("\n\n---\n\n");
    const blob = new Blob([content], { type: format === "md" ? "text/markdown" : "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `chat-export-${Date.now()}.${format}`; a.click();
    URL.revokeObjectURL(url);
  };

  // command suggestions
  const onInputChange = (val: string) => {
    setInput(val);
    if (val.startsWith("/") && !val.includes(" ")) { setCmdOpen(true); setCmdQuery(val.slice(1)); setCmdIndex(0); } else { setCmdOpen(false); }
  };
  const onCommandSelect = (cmdId: string) => { setInput(`/${cmdId} `); setCmdOpen(false); setPaletteOpen(false); };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (cmdOpen) {
      if (e.key === "ArrowDown") { e.preventDefault(); setCmdIndex(i => i + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setCmdIndex(i => Math.max(0, i - 1)); }
      else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const matches = COMMANDS.filter(c => c.id.includes(cmdQuery) || c.label.toLowerCase().includes(cmdQuery.toLowerCase()));
        if (matches[cmdIndex]) onCommandSelect(matches[cmdIndex].id);
      } else if (e.key === "Escape") setCmdOpen(false);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  // --- input bar (shared between empty & active states) ---
  const renderInputBar = (isHome: boolean) => (
    <div className={isHome ? "chat-input-home" : "chat-input-home"} style={!isHome ? { borderRadius: "0.75rem" } : undefined}>
      <textarea
        value={input}
        onChange={e => onInputChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask Junas anything..."
        rows={isHome ? 4 : 1}
        style={!isHome ? { minHeight: "44px", maxHeight: "200px", padding: "0.75rem 1rem 0.35rem" } : undefined}
      />
      <div className="chat-input-toolbar">
        <div className="toolbar-left">
          <input type="file" ref={fileInputRef} accept=".pdf,.docx,.txt,.md" onChange={handleFileUpload} style={{ display: "none" }} />
          <button type="button" className="toolbar-btn" onClick={() => fileInputRef.current?.click()} title="Attach document">
            + Files
          </button>
          <div className="toolbar-divider" />
          <span className="toolbar-hint">/ for commands · Cmd+K palette</span>
        </div>
        <div className="toolbar-right">
          <ProviderSelector value={provider} onChange={setProvider} />
          <button type="button" className="ask-btn" onClick={() => sendMessage()} disabled={streaming}>
            {streaming ? "..." : "Ask Junas"}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="chat-page">
      {isEmpty ? (
        /* --- EMPTY STATE: centered Harvey-style input --- */
        <div className="chat-home">
          <div className="chat-home-inner">
            <div style={{ position: "relative" }}>
              <CommandSuggestions query={cmdQuery} onSelect={onCommandSelect} isOpen={cmdOpen} selectedIndex={cmdIndex} />
              {pendingFile && (
                <div className="pending-file">
                  <span>{pendingFile.name} ({pendingFile.text.length.toLocaleString()} chars)</span>
                  <button type="button" className="pending-file-remove" onClick={() => setPendingFile(null)}>&times;</button>
                </div>
              )}
              {renderInputBar(true)}
            </div>
          </div>
        </div>
      ) : (
        /* --- ACTIVE CONVERSATION --- */
        <div className="chat-active">
          {/* top bar */}
          <div className="chat-top-bar">
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span className="chat-top-title">Chat</span>
              {leaves.length > 1 && <span className="badge muted" style={{ fontSize: "0.68rem" }}>{leaves.length} branches</span>}
            </div>
            <div className="chat-top-actions">
              {(["chat", "tree"] as Tab[]).map(t => (
                <button key={t} type="button" className="chat-top-btn" onClick={() => setActiveTab(t)}
                  style={activeTab === t ? { background: "#F5F5F4", fontWeight: 600 } : undefined}>
                  {t === "tree" ? "Graph" : "Chat"}
                </button>
              ))}
              <button type="button" className="chat-top-btn" onClick={() => exportChat("md")}>Export</button>
            </div>
          </div>

          {activeTab === "chat" ? (
            <>
              {/* message thread */}
              <div className="chat-messages">
                {messages.map(m => {
                  const sibs = getBranchSiblings(nodeMap, m.id);
                  const sibIdx = sibs.indexOf(m.id);
                  const hasBranches = sibs.length > 1;
                  return (
                    <div key={m.id} className={`chat-msg ${m.role === "user" ? "chat-msg-user" : "chat-msg-assistant"}`}>
                      <div className="chat-msg-role">
                        <span>{m.role === "user" ? "You" : "Junas"}</span>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                          {hasBranches && (
                            <div className="branch-nav">
                              <button type="button" onClick={() => switchBranch(m.id, "prev")} disabled={sibIdx === 0}>&lt;</button>
                              <span style={{ fontFamily: "var(--font-mono, monospace)" }}>{sibIdx + 1}/{sibs.length}</span>
                              <button type="button" onClick={() => switchBranch(m.id, "next")} disabled={sibIdx === sibs.length - 1}>&gt;</button>
                            </div>
                          )}
                        </div>
                      </div>
                      {editingId === m.id ? (
                        <div>
                          <textarea className="edit-textarea" value={editContent} onChange={e => setEditContent(e.target.value)} rows={3} />
                          <div className="edit-actions">
                            <button type="button" className="edit-save" onClick={saveEdit}>Save & Branch</button>
                            <button type="button" className="edit-cancel" onClick={() => setEditingId(null)}>Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <div className="chat-msg-body">
                          {m.role === "assistant" ? (
                            <Suspense fallback={<div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>}>
                              <LegalMarkdownRenderer content={m.content} />
                            </Suspense>
                          ) : <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>}
                        </div>
                      )}
                      {/* actions */}
                      {!editingId && m.content && (
                        <div className="chat-msg-actions">
                          <button type="button" className="chat-msg-action-btn" onClick={() => navigator.clipboard.writeText(m.content)}>Copy</button>
                          {m.role === "user" && (
                            <button type="button" className="chat-msg-action-btn" onClick={() => startEdit(m.id)}>Edit</button>
                          )}
                          {m.role === "assistant" && extractArtifacts(m.content).length > 0 && (
                            <button type="button" className="artifact-btn" onClick={() => setArtifactsContent(m.content)}>
                              Artifacts ({extractArtifacts(m.content).length})
                            </button>
                          )}
                          {m.role === "assistant" && m.responseTimeMs && (
                            <TokenCounter content={m.content} isStreaming={streaming && m.id === currentLeafId} provider={provider} responseTimeMs={m.responseTimeMs} />
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                {streaming && (
                  <div className="streaming-indicator">
                    <div className="streaming-dots"><span /><span /><span /></div>
                    <span>Generating...</span>
                    <button type="button" className="stop-btn" onClick={stopGeneration}>Stop</button>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* bottom input bar */}
              <div className="chat-input-bar">
                <div className="chat-input-bar-inner">
                  {pendingFile && (
                    <div className="pending-file">
                      <span>{pendingFile.name} ({pendingFile.text.length.toLocaleString()} chars)</span>
                      <button type="button" className="pending-file-remove" onClick={() => setPendingFile(null)}>&times;</button>
                    </div>
                  )}
                  <div style={{ position: "relative" }}>
                    <CommandSuggestions query={cmdQuery} onSelect={onCommandSelect} isOpen={cmdOpen} selectedIndex={cmdIndex} />
                    {renderInputBar(false)}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div style={{ flex: 1, overflow: "hidden" }}>
              <Suspense fallback={<div className="meta-line" style={{ padding: "1.5rem" }}>Loading graph...</div>}>
                <ForceGraph nodeMap={nodeMap} currentLeafId={currentLeafId} onSelectNode={onSelectNode} />
              </Suspense>
            </div>
          )}
        </div>
      )}

      {/* modals */}
      <Suspense fallback={null}>
        <CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} onSelectCommand={onCommandSelect} onNewChat={newChat} />
      </Suspense>
      <ArtifactsPanel isOpen={!!artifactsContent} onClose={() => setArtifactsContent("")} content={artifactsContent} />
    </div>
  );
}
