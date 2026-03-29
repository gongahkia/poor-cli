// conversation history — search, list, restore
import { rpc } from './rpc.js';

let debounceTimer = null;

export async function initHistory() {
  const searchInput = document.getElementById('history-search');
  const list = document.getElementById('history-list');
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => searchConversations(searchInput.value, list), 300);
  });
  await loadHistory(list);
}

async function loadHistory(list) {
  list.innerHTML = '';
  try {
    const result = await rpc('list_history', {});
    const items = result.messages || result.sessions || result || [];
    renderHistoryItems(list, items);
  } catch (e) {
    list.innerHTML = `<p style="color:var(--error)">Failed to load history: ${e}</p>`;
  }
}

async function searchConversations(term, list) {
  if (!term.trim()) return loadHistory(list);
  list.innerHTML = '';
  try {
    const result = await rpc('search_history', { term, limit: 20 });
    const items = result.results || result.messages || result || [];
    renderHistoryItems(list, items);
  } catch (e) { console.warn('[history] search_history:', e); }
}

function renderHistoryItems(container, items) {
  if (!items.length) {
    container.innerHTML = '<p style="color:var(--text-muted)">No conversations found</p>';
    return;
  }
  items.forEach(item => {
    const card = document.createElement('div');
    card.className = 'item-card';
    const preview = item.content || item.text || item.label || item.sessionId || '';
    const date = item.timestamp || item.createdAt || '';
    card.innerHTML = `<h3>${esc(preview.slice(0, 60))}${preview.length > 60 ? '...' : ''}</h3><p>${esc(date)}</p>`;
    card.addEventListener('click', () => {
      if (item.sessionId) rpc('restore_session', { sessionId: item.sessionId }).catch(e => console.warn('[history] restore_session:', e));
    });
    container.appendChild(card);
  });
}

export async function refreshHistorySidebar() {
  const sidebar = document.getElementById('history-sidebar-list');
  if (!sidebar) return;
  try {
    const result = await rpc('list_history', {});
    const items = (result.messages || result.sessions || result || []).slice(0, 5);
    sidebar.innerHTML = '';
    items.forEach(item => {
      const div = document.createElement('div');
      div.className = 'history-sidebar-item';
      div.textContent = (item.content || item.label || item.sessionId || '').slice(0, 40);
      sidebar.appendChild(div);
    });
  } catch (e) { console.warn('[history] list_history:', e); }
}

function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
