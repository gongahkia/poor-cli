// multiplayer / collaboration panel
import { rpc } from './rpc.js';
import { notify } from './notifications.js';

const cpIdle = document.getElementById('cp-idle');
const cpActive = document.getElementById('cp-active');
const cpJoinBtn = document.getElementById('cp-join-btn');
const cpInviteInput = document.getElementById('cp-invite-input');
const cpLeaveBtn = document.getElementById('cp-leave-btn');
const cpInviteBtn = document.getElementById('cp-invite-btn');
const cpStartStatus = document.getElementById('cp-start-status');

let sessionActive = false;

export function initCollabPanel() {
  if (cpJoinBtn) cpJoinBtn.addEventListener('click', joinSession);
  if (cpLeaveBtn) cpLeaveBtn.addEventListener('click', leaveSession);
  if (cpInviteBtn) cpInviteBtn.addEventListener('click', shareInvite);
  document.querySelectorAll('.cp-preset-btns button[data-preset]').forEach(btn => {
    btn.addEventListener('click', () => startSession(btn.dataset.preset));
  });
}

export function toggleCollabPanel() {}
export function showCollabButton() {}

export function cleanupCollab() {
  if (sessionActive) {
    rpc('leave_remote_session', {}).catch(e => console.warn('[multiplayer] leave_remote_session:', e));
    sessionActive = false;
  }
}

function showStatus(msg, isError) {
  if (!cpStartStatus) return;
  cpStartStatus.hidden = false;
  cpStartStatus.textContent = msg;
  cpStartStatus.style.color = isError ? 'var(--error)' : 'var(--success)';
  if (!isError) setTimeout(() => { cpStartStatus.hidden = true; }, 3000);
}

async function startSession(preset) {
  showStatus(`Starting ${preset} session...`, false);
  try {
    const result = await rpc('pair_start', { preset: preset || 'pairing' });
    sessionActive = true;
    if (cpIdle) cpIdle.hidden = true;
    if (cpActive) cpActive.hidden = false;
    // show session info
    const infoEl = document.getElementById('cp-session-info');
    if (infoEl) {
      const room = result.room || result.sessionId || preset;
      infoEl.innerHTML = `<h4>Active Session</h4>`
        + `<div class="item-card"><div class="item-card-header"><h3>${esc(preset)}</h3><span class="badge badge-ok">active</span></div>`
        + `<p class="item-card-meta">Room: ${esc(room)}</p></div>`;
    }
    await refreshMembers();
  } catch (e) {
    const msg = `Failed to start: ${e}`;
    showStatus(msg, true);
    notify({ title: 'Collab failed', body: msg, type: 'error' });
  }
}

async function joinSession() {
  const code = (cpInviteInput?.value || '').trim();
  if (!code) return;
  showStatus('Joining...', false);
  try {
    await rpc('join_remote_session', { invite_code: code });
    sessionActive = true;
    if (cpIdle) cpIdle.hidden = true;
    if (cpActive) cpActive.hidden = false;
    await refreshMembers();
  } catch (e) {
    const msg = `Failed to join: ${e}`;
    showStatus(msg, true);
    notify({ title: 'Collab join failed', body: msg, type: 'error' });
  }
}

async function leaveSession() {
  try { await rpc('leave_remote_session', {}); } catch (e) { console.warn('[multiplayer] leaveSession:', e); }
  sessionActive = false;
  if (cpIdle) cpIdle.hidden = false;
  if (cpActive) cpActive.hidden = true;
}

async function shareInvite() {
  try {
    const result = await rpc('rotate_host_token', {});
    const code = result.invite_code || result.token || JSON.stringify(result);
    const modal = document.getElementById('invite-modal');
    const display = document.getElementById('invite-code-display');
    if (modal && display) {
      display.value = code;
      modal.hidden = false;
    }
  } catch (e) {
    notify({ title: 'Invite failed', body: String(e), type: 'error' });
  }
}

async function refreshMembers() {
  try {
    const result = await rpc('list_host_members', {});
    const members = result.members || result || [];
    const el = document.getElementById('cp-members');
    if (!el) return;
    if (!members.length) {
      el.innerHTML = '<h4>Members</h4><p class="view-empty-text">No members yet — share your invite code</p>';
      return;
    }
    el.innerHTML = '<h4>Members</h4>' + members.map(m =>
      `<div class="cp-member"><span>${esc(m.name || m.id || '?')}</span><span class="badge">${esc(m.role || '')}</span></div>`
    ).join('');
  } catch (e) { console.warn('[multiplayer] refreshMembers:', e); }
}

// invite modal handlers (guarded)
const inviteClose = document.getElementById('invite-modal-close');
const inviteCopy = document.getElementById('invite-modal-copy');
if (inviteClose) inviteClose.addEventListener('click', () => { document.getElementById('invite-modal').hidden = true; });
if (inviteCopy) inviteCopy.addEventListener('click', () => {
  const ta = document.getElementById('invite-code-display');
  if (ta) navigator.clipboard.writeText(ta.value).catch(e => { console.warn('[multiplayer] clipboard:', e); ta.select(); document.execCommand('copy'); });
});

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
