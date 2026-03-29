// session management panel
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initSessions() {
  const container = document.getElementById('sessions-content');
  if (!container) return;
  container.innerHTML = '';
  const header = document.createElement('div');
  header.className = 'view-toolbar';
  header.innerHTML = `<button class="btn btn-sm btn-primary" id="sessions-create-btn">+ New Session</button>`;
  const list = document.createElement('div');
  list.id = 'sessions-list';
  list.className = 'item-list';
  container.appendChild(header);
  container.appendChild(list);
  document.getElementById('sessions-create-btn').onclick = createSession;
  await refreshSessions();
}

export async function refreshSessions() {
  const list = document.getElementById('sessions-list');
  if (!list) return;
  list.innerHTML = '';
  try {
    const result = await rpc('list_sessions', {});
    const sessions = result.sessions || result || [];
    if (!sessions.length) { list.innerHTML = '<div class="view-empty"><p>No sessions</p></div>'; return; }
    sessions.forEach(s => {
      const card = document.createElement('div');
      card.className = 'item-card';
      const sid = s.sessionId || s.id;
      const active = s.isDefault || s.isActive;
      card.innerHTML = `<div class="item-card-header">`
        + `<h3>${esc(s.label || sid)}</h3>`
        + (active ? '<span class="badge badge-ok">active</span>' : '<span class="badge">idle</span>')
        + `</div>`
        + `<p class="item-card-meta">ID: ${esc(sid)} &middot; Messages: ${s.messageCount || s.messages || '—'}</p>`
        + `<div class="item-card-actions">`
        + `<button class="btn btn-sm" data-act="switch">Switch</button>`
        + `<button class="btn btn-sm" data-act="rename">Rename</button>`
        + `<button class="btn btn-sm" data-act="save">Save</button>`
        + `<button class="btn btn-sm" data-act="restore">Restore</button>`
        + `<button class="btn btn-sm btn-danger" data-act="destroy">Destroy</button>`
        + `</div>`;
      card.querySelector('[data-act="switch"]').onclick = () => sessionAction('switch_session', { session_id: sid });
      card.querySelector('[data-act="rename"]').onclick = async () => {
        const name = prompt('New name:', s.label || '');
        if (name === null) return;
        await sessionAction('rename_session', { session_id: sid, label: name });
      };
      card.querySelector('[data-act="save"]').onclick = () => sessionAction('save_session', {});
      card.querySelector('[data-act="restore"]').onclick = () => sessionAction('restore_session', {});
      card.querySelector('[data-act="destroy"]').onclick = async () => {
        if (!confirm(`Destroy session "${s.label || sid}"?`)) return;
        await sessionAction('destroy_session', { session_id: sid });
      };
      list.appendChild(card);
    });
  } catch (e) {
    console.warn('[sessions] list_sessions:', e);
    list.innerHTML = '<div class="view-empty"><p>Sessions unavailable — backend not connected</p></div>';
  }
}

async function sessionAction(cmd, params) {
  try {
    await rpc(cmd, params);
    await refreshSessions();
  } catch (e) { addMessage(`Session action failed: ${e}`, 'assistant'); }
}

async function createSession() {
  const label = prompt('Session name:');
  if (label === null) return;
  try {
    await rpc('create_session', { label: label || `session-${Date.now()}` });
    await refreshSessions();
  } catch (e) { addMessage(`Create session failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
