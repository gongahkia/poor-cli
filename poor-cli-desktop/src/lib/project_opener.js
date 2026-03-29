/**
 * Open Project — create a new session targeting any folder on disk.
 * Uses the native OS file picker (Tauri dialog plugin) to select a folder,
 * then creates a session with that folder as the working directory.
 */

import { rpc } from './rpc.js';
import { showView } from './views.js';
import { notify } from './notifications.js';

let _dialog = null;

async function getDialog() {
  if (_dialog) return _dialog;
  try {
    _dialog = window.__TAURI__?.dialog || (await import('@tauri-apps/plugin-dialog'));
  } catch (e) { console.warn('[project_opener] getDialog:', e); _dialog = null; }
  return _dialog;
}

export function initProjectOpener() {
  const sidebarBtn = document.getElementById('open-project-btn');
  if (sidebarBtn) sidebarBtn.addEventListener('click', openProjectDialog);
  const tabBtn = document.getElementById('open-project-tab-btn');
  if (tabBtn) tabBtn.addEventListener('click', openProjectDialog);
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'o') {
      e.preventDefault();
      openProjectDialog();
    }
  });
}

export async function openProjectDialog() {
  const dialog = await getDialog();
  if (dialog?.open) {
    try {
      const selected = await dialog.open({ directory: true, multiple: false, title: 'Open Project Folder' });
      if (selected) {
        const path = typeof selected === 'string' ? selected : selected.path || selected;
        if (path) { await openProject(path); return; }
      }
      return; // user cancelled
    } catch (e) { console.warn('[project_opener] openProjectDialog:', e); /* fall through to custom modal */ }
  }
  openFallbackDialog(); // no dialog plugin available
}

function openFallbackDialog() {
  let overlay = document.getElementById('project-opener-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'project-opener-overlay';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="project-opener-modal">
        <div class="po-header">
          <h3>Open Project</h3>
          <button class="po-close">&times;</button>
        </div>
        <div class="po-body">
          <label class="po-label">Folder path</label>
          <input class="po-path-input" type="text" placeholder="/path/to/project" autofocus />
          <div class="po-hint">Enter the full path to a project folder.</div>
          <div class="po-recents" id="po-recents"></div>
        </div>
        <div class="po-footer">
          <button class="btn btn-primary po-open-btn">Open</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('.po-close').onclick = closeDialog;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closeDialog(); });
    const input = overlay.querySelector('.po-path-input');
    const openBtn = overlay.querySelector('.po-open-btn');
    openBtn.addEventListener('click', () => { const p = input.value.trim(); if (p) openProject(p); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); const p = input.value.trim(); if (p) openProject(p); }
      if (e.key === 'Escape') closeDialog();
    });
  }
  overlay.classList.remove('hidden');
  overlay.style.display = '';
  const input = overlay.querySelector('.po-path-input');
  input.value = '';
  input.focus();
  renderRecents();
}

function closeDialog() {
  const overlay = document.getElementById('project-opener-overlay');
  if (overlay) { overlay.classList.add('hidden'); overlay.style.display = 'none'; }
}

async function openProject(folderPath) {
  closeDialog();
  saveRecent(folderPath);
  try {
    const label = folderPath.split('/').pop() || folderPath;
    const result = await rpc('create_session', { label, working_directory: folderPath, make_default: true });
    const session = result?.session || result;
    const sid = session?.sessionId || session?.id;
    if (sid) {
      await rpc('switch_session', { session_id: sid }).catch(e => console.warn('[project_opener] switch_session:', e));
    }
    try {
      const app = await import('./app.js');
      await app.refreshSessions();
      // force-select the new session in the UI
      const threadTitle = document.getElementById('thread-title');
      if (threadTitle) threadTitle.textContent = label;
      // highlight the correct tab
      document.querySelectorAll('.session-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.sessionId === sid);
      });
      document.querySelectorAll('.vtab-item').forEach(vt => {
        vt.classList.toggle('active', vt.textContent.trim() === label);
      });
    } catch (e) { console.warn('[project_opener] refreshSessions:', e); }
    showView('chat');
    // clear chat for fresh session
    const chatMessages = document.getElementById('chat-messages');
    if (chatMessages) {
      chatMessages.innerHTML = `<div class="welcome-message"><h1>${label}</h1><p>Project opened — type a message to start</p></div>`;
    }
  } catch (e) {
    notify({ title: 'Open project failed', body: `${e.message || e}`, type: 'error' });
  }
}

// ── recents ─────────────────────────────────────────────────────────
const RECENTS_KEY = 'poor-cli-recent-projects';
const MAX_RECENTS = 8;
function getRecents() { try { return JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]'); } catch (e) { console.warn('[project_opener] getRecents:', e); return []; } }
function saveRecent(path) {
  let recents = getRecents().filter(p => p !== path);
  recents.unshift(path);
  recents = recents.slice(0, MAX_RECENTS);
  localStorage.setItem(RECENTS_KEY, JSON.stringify(recents));
}
function renderRecents() {
  const container = document.getElementById('po-recents');
  if (!container) return;
  const recents = getRecents();
  if (!recents.length) { container.innerHTML = ''; return; }
  let html = '<div class="po-recents-label">Recent projects</div>';
  for (const path of recents) {
    const name = path.split('/').pop() || path;
    html += `<div class="po-recent-item" data-path="${esc(path)}">
      <span class="po-recent-name">${esc(name)}</span>
      <span class="po-recent-path">${esc(path)}</span>
    </div>`;
  }
  container.innerHTML = html;
  container.querySelectorAll('.po-recent-item').forEach(el => {
    el.onclick = () => openProject(el.dataset.path);
  });
}
function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
