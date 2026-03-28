/**
 * Open Project — create a new session targeting any folder on disk.
 *
 * Shows a modal where the user enters a folder path. Creates a new
 * session with that folder as the working directory, then auto-sends
 * /workspace-map to load the project's structure as context.
 */

import { rpc } from './rpc.js';
import { showView } from './views.js';

export function initProjectOpener() {
  // sidebar button
  const sidebarBtn = document.getElementById('open-project-btn');
  if (sidebarBtn) sidebarBtn.addEventListener('click', openProjectDialog);

  // tab bar button
  const tabBtn = document.getElementById('open-project-tab-btn');
  if (tabBtn) tabBtn.addEventListener('click', openProjectDialog);

  // keyboard shortcut: Cmd+O
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'o') {
      e.preventDefault();
      openProjectDialog();
    }
  });
}

function openProjectDialog() {
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
          <div class="po-hint">Enter the full path to a project folder. A new session will be created with this folder as the working directory.</div>
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

    openBtn.addEventListener('click', () => {
      const path = input.value.trim();
      if (path) openProject(path);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const path = input.value.trim();
        if (path) openProject(path);
      }
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
  // save to recents
  saveRecent(folderPath);

  try {
    // create a new session with the folder as cwd
    // try both RPC name styles for compatibility
    let result;
    try {
      result = await rpc('poor-cli/createSession', { label: folderPath.split('/').pop() || folderPath, workingDirectory: folderPath, makeDefault: true });
    } catch {
      result = await rpc('create_session', { label: folderPath.split('/').pop() || folderPath, workingDirectory: folderPath, makeDefault: true });
    }
    const session = result?.session || result;

    if (session?.sessionId) {
      try { await rpc('poor-cli/switchSession', { sessionId: session.sessionId }); }
      catch { await rpc('switch_session', { session_id: session.sessionId }).catch(() => {}); }
    }

    // refresh the UI
    try {
      const { refreshSessions } = await import('./app.js');
      await refreshSessions();
    } catch {}

    // switch to chat and send /workspace-map to load context
    showView('chat');
    setTimeout(() => {
      const input = document.getElementById('chat-input');
      const sendBtn = document.getElementById('send-btn');
      if (input && sendBtn) {
        input.value = '/workspace-map';
        sendBtn.click();
      }
    }, 500);

  } catch (e) {
    alert(`Failed to open project: ${e.message || e}`);
  }
}

// ── recents ─────────────────────────────────────────────────────────

const RECENTS_KEY = 'poor-cli-recent-projects';
const MAX_RECENTS = 8;

function getRecents() {
  try { return JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]'); } catch { return []; }
}

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
