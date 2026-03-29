// multiplayer / collaboration panel
import { rpc } from './rpc.js';

const collabPanel = document.getElementById('collab-panel');
const cpClose = document.getElementById('cp-close');
const cpIdle = document.getElementById('cp-idle');
const cpActive = document.getElementById('cp-active');
const cpJoinBtn = document.getElementById('cp-join-btn');
const cpInviteInput = document.getElementById('cp-invite-input');
const cpLeaveBtn = document.getElementById('cp-leave-btn');
const cpInviteBtn = document.getElementById('cp-invite-btn');
const wbCollab = document.getElementById('wb-collab');

let sessionActive = false;

export function initCollabPanel() {
  cpClose.addEventListener('click', () => collabPanel.classList.add('collapsed'));
  cpJoinBtn.addEventListener('click', joinSession);
  cpLeaveBtn.addEventListener('click', leaveSession);
  cpInviteBtn.addEventListener('click', shareInvite);
  document.querySelectorAll('.cp-preset-btns button').forEach(btn => {
    btn.addEventListener('click', () => startSession(btn.dataset.preset));
  });
}

export function toggleCollabPanel() {
  collabPanel.classList.toggle('collapsed');
}

export function showCollabButton() {
  // show the collab button in workspace bar
}

export function cleanupCollab() {
  if (sessionActive) {
    rpc('leave_remote_session', {}).catch(() => {});
    sessionActive = false;
  }
}

async function startSession(preset) {
  try {
    await rpc('pair_start', { preset: preset || 'pairing' });
    sessionActive = true;
    cpIdle.hidden = true;
    cpActive.hidden = false;
    wbCollab.hidden = false;
    await refreshMembers();
  } catch (e) { console.error('collab start failed:', e); }
}

async function joinSession() {
  const code = cpInviteInput.value.trim();
  if (!code) return;
  try {
    await rpc('join_remote_session', { invite_code: code });
    sessionActive = true;
    cpIdle.hidden = true;
    cpActive.hidden = false;
    wbCollab.hidden = false;
    await refreshMembers();
  } catch (e) { console.error('collab join failed:', e); }
}

async function leaveSession() {
  try {
    await rpc('leave_remote_session', {});
  } catch (_) {}
  sessionActive = false;
  cpIdle.hidden = false;
  cpActive.hidden = true;
  wbCollab.hidden = true;
}

async function shareInvite() {
  try {
    const result = await rpc('rotate_host_token', {});
    const code = result.invite_code || result.token || JSON.stringify(result);
    document.getElementById('invite-code-display').value = code;
    document.getElementById('invite-modal').hidden = false;
  } catch (e) { console.error('invite failed:', e); }
}

async function refreshMembers() {
  try {
    const result = await rpc('list_host_members', {});
    const members = result.members || result || [];
    const el = document.getElementById('cp-members');
    el.innerHTML = members.map(m =>
      `<div class="cp-member"><span>${esc(m.name || m.id || '?')}</span><span class="badge">${esc(m.role || '')}</span></div>`
    ).join('') || '<p style="color:var(--text-muted)">No members</p>';
  } catch (_) {}
}

document.getElementById('invite-modal-close').addEventListener('click', () => { document.getElementById('invite-modal').hidden = true; });
document.getElementById('invite-modal-copy').addEventListener('click', () => {
  const ta = document.getElementById('invite-code-display');
  navigator.clipboard.writeText(ta.value).catch(() => { ta.select(); document.execCommand('copy'); });
});

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
