// session management panel
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initSessions() {
  const container = document.getElementById('sessions-content');
  if (!container) return;
  const header = document.createElement('div');
  header.innerHTML = `<button class="btn btn-sm btn-primary" id="sessions-create-btn">+ New Session</button>`;
  const list = document.createElement('div');
  list.id = 'sessions-list';
  list.className = 'item-list';
  container.innerHTML = '';
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
    const result = await rpc('poor-cli/listMuxSessions', {});
    const sessions = result.sessions || result || [];
    if (!sessions.length) { list.innerHTML = '<p style="color:var(--text-muted)">No sessions</p>'; return; }
    sessions.forEach(s => {
      const card = document.createElement('div');
      card.className = 'item-card';
      const sid = s.sessionId || s.id;
      const active = s.isDefault || s.isActive;
      card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
        + `<h3>${esc(s.label || sid)}</h3>`
        + (active ? '<span class="badge badge-success">active</span>' : '<span class="badge">idle</span>')
        + `</div>`
        + `<p style="color:var(--text-muted);font-size:12px">`
        + `ID: ${esc(sid)} | Messages: ${s.messageCount || s.messages || '—'}`
        + `</p>`
        + `<div class="session-actions" style="display:flex;gap:4px;margin-top:4px">`
        + `<button class="btn btn-sm" data-act="switch">Switch</button>`
        + `<button class="btn btn-sm" data-act="fork">Fork</button>`
        + `<button class="btn btn-sm" data-act="rename">Rename</button>`
        + `<button class="btn btn-sm" data-act="save">Save</button>`
        + `<button class="btn btn-sm" data-act="restore">Restore</button>`
        + `<button class="btn btn-sm" data-act="destroy" style="color:var(--error)">Destroy</button>`
        + `</div>`;
      card.querySelector('[data-act="switch"]').onclick = () => sessionAction('poor-cli/switchSession', { sessionId: sid });
      card.querySelector('[data-act="fork"]').onclick = () => sessionAction('poor-cli/forkSession', { sourceSessionId: sid, copyHistory: true });
      card.querySelector('[data-act="rename"]').onclick = async () => {
        const name = prompt('New name:', s.label || '');
        if (name === null) return;
        await sessionAction('poor-cli/renameSession', { sessionId: sid, label: name });
      };
      card.querySelector('[data-act="save"]').onclick = () => sessionAction('poor-cli/saveSession', { sessionId: sid });
      card.querySelector('[data-act="restore"]').onclick = () => sessionAction('poor-cli/restoreSession', { sessionId: sid });
      card.querySelector('[data-act="destroy"]').onclick = async () => {
        if (!confirm(`Destroy session "${s.label || sid}"?`)) return;
        await sessionAction('poor-cli/destroySession', { sessionId: sid });
      };
      list.appendChild(card);
    });
  } catch (_) {
    list.innerHTML = '<p style="color:var(--text-muted)">Sessions unavailable — backend not connected</p>';
  }
}

async function sessionAction(method, params) {
  try {
    await rpc(method, params);
    await refreshSessions();
  } catch (e) { addMessage(`Session action failed: ${e}`, 'assistant'); }
}

async function createSession() {
  const label = prompt('Session name:');
  if (label === null) return;
  try {
    await rpc('poor-cli/createSession', { label: label || `session-${Date.now()}` });
    await refreshSessions();
  } catch (e) { addMessage(`Create session failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
