/**
 * Conversation persistence — localStorage-based save/load/list/delete for chat trees.
 */
import type { NodeMap, TreeMessage } from "./chat-tree";

export interface ConversationMeta {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

interface StoredConversation {
  meta: ConversationMeta;
  nodeMap: NodeMap;
  currentLeafId: string;
}

const META_KEY = "junas_conv_meta";

function metaListKey(): ConversationMeta[] {
  try { return JSON.parse(localStorage.getItem(META_KEY) || "[]"); }
  catch { return []; }
}
function saveMetaList(list: ConversationMeta[]) {
  localStorage.setItem(META_KEY, JSON.stringify(list));
}

export function generateConversationId(): string {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function saveConversation(id: string, nodeMap: NodeMap, currentLeafId: string) {
  const messages = Object.values(nodeMap);
  const firstUser = messages.find((m) => m.role === "user");
  const title = firstUser ? firstUser.content.slice(0, 60).replace(/\n/g, " ") : "Untitled";
  const stored: StoredConversation = { meta: { id, title, createdAt: 0, updatedAt: Date.now(), messageCount: messages.length }, nodeMap, currentLeafId };
  // preserve original createdAt
  const existing = loadConversation(id);
  stored.meta.createdAt = existing?.meta.createdAt || Date.now();
  localStorage.setItem(`junas_conv_${id}`, JSON.stringify(stored));
  // update meta list
  const list = metaListKey().filter((m) => m.id !== id);
  list.unshift(stored.meta);
  saveMetaList(list);
}

export function loadConversation(id: string): StoredConversation | null {
  try {
    const raw = localStorage.getItem(`junas_conv_${id}`);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch { return null; }
}

export function listConversations(): ConversationMeta[] {
  return metaListKey().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function deleteConversation(id: string) {
  localStorage.removeItem(`junas_conv_${id}`);
  const list = metaListKey().filter((m) => m.id !== id);
  saveMetaList(list);
}
