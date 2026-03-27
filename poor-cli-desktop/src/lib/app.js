// poor-cli desktop — frontend app logic
import { rpc } from './rpc.js';
import { registerView, showView } from './views.js';
import { renderMarkdown } from './markdown.js';
import { initSettings, applyCustomFonts } from './settings.js';
import { initSkills } from './skills.js';
import { initHistory, refreshHistorySidebar } from './history.js';
import { initFileChangesPanel, updateFileChanges, openFileChangesPanel, toggleFileChangesPanel } from './filechanges.js';
import { initCollabPanel, toggleCollabPanel, showCollabButton, cleanupCollab } from './multiplayer.js';
import { initAutocomplete } from './autocomplete.js';

const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const providerSelect = document.getElementById('provider-select');
const providerInfo = document.getElementById('provider-info');
const threadTitle = document.getElementById('thread-title');
const threadMenuBtn = document.getElementById('thread-menu-btn');
const threadMenu = document.getElementById('thread-menu');
const settingsBack = document.getElementById('settings-back');
const sbCwd = document.getElementById('sb-cwd');
const sbPermission = document.getElementById('sb-permission');
const sbGit = document.getElementById('sb-git');
const sbSpinner = document.getElementById('sb-spinner');
const sbChanges = document.getElementById('sb-changes');
const sessionTabBar = document.getElementById('session-tab-bar');
const sessionTabAdd = document.getElementById('session-tab-add');
const projectAvatar = document.getElementById('project-avatar');
const projectName = document.getElementById('project-name');
const projectPath = document.getElementById('project-path');
const wbGitBranch = document.getElementById('wb-git-branch');
const wbPermission = document.getElementById('wb-permission-mode');
const wbFileChanges = document.getElementById('wb-file-changes');
const wbFcCount = document.getElementById('wb-fc-count');
const wbFcAdded = document.getElementById('wb-fc-added');
const wbFcRemoved = document.getElementById('wb-fc-removed');
const newSessionModal = document.getElementById('new-session-modal');
const newSessionNameInput = document.getElementById('new-session-name');
const modalCancel = document.getElementById('modal-cancel');
const modalCreate = document.getElementById('modal-create');

let initialized = false;
let activeSessionId = null;

// helpers
function relativeTime(iso) {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return 'now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message message-${role}`;
  if (role === 'assistant') {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function clearWelcome() {
  const w = chatMessages.querySelector('.welcome-message');
  if (w) w.remove();
}

// init
async function ensureInitialized() {
  if (initialized) return;
  try {
    const storedKeys = JSON.parse(localStorage.getItem('poor-cli-api-keys') || '{}');
    const envKeys = {};
    const envMap = { gemini: 'GEMINI_API_KEY', openai: 'OPENAI_API_KEY', anthropic: 'ANTHROPIC_API_KEY', ollama: 'OLLAMA_API_KEY', brave: 'BRAVE_SEARCH_API_KEY' };
    for (const [id, key] of Object.entries(storedKeys)) { if (key && envMap[id]) envKeys[envMap[id]] = key; }
    await rpc('initialize_backend', { env_keys: envKeys });
    initialized = true;
    showCollabButton();
    await Promise.all([refreshProviderInfo(), refreshSessions(), refreshStatusBar(), refreshHistorySidebar()]);
  } catch (e) {
    const msg = String(e);
    if (msg.includes('timeout') || msg.includes('spawn') || msg.includes('No such file')) {
      providerInfo.innerHTML = '<span style="color:var(--warning)">Server not running</span> — check Python venv';
    } else {
      providerInfo.textContent = `Error: ${msg}`;
    }
  }
}

// provider
let activeProvider = null;
async function refreshProviderInfo() {
  try {
    const info = await rpc('get_provider_info', {});
    const name = info.name || 'unknown';
    const model = info.model || 'unknown';
    providerInfo.textContent = `${name} / ${model}`;
    activeProvider = name;
    providerSelect.value = name; // sync dropdown to actual backend provider
  } catch (e) {
    providerInfo.textContent = 'Not connected';
  }
}

// sessions
function abbreviatePath(p) {
  if (!p) return '';
  const parts = p.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return p;
  return '.../' + parts.slice(-2).join('/');
}

export async function refreshSessions() {
  try {
    const result = await rpc('list_sessions', {});
    const sessions = result.sessions || [];
    sessionTabBar.querySelectorAll('.session-tab').forEach(el => el.remove());
    const addBtn = sessionTabBar.querySelector('.session-tab-add');
    sessions.forEach(s => {
      const tab = document.createElement('div');
      tab.className = `session-tab${s.isDefault ? ' active' : ''}`;
      const dot = document.createElement('span');
      dot.className = `status-dot ${s.status === 'active' || s.status === 'running' ? 'running' : s.status === 'idle' ? 'idle' : 'stopped'}`;
      tab.appendChild(dot);
      const name = document.createElement('span');
      name.className = 'tab-name';
      name.textContent = s.label || s.sessionId;
      tab.appendChild(name);
      if (s.workingDirectory) {
        const pathSpan = document.createElement('span');
        pathSpan.className = 'tab-path';
        pathSpan.textContent = abbreviatePath(s.workingDirectory);
        tab.appendChild(pathSpan);
      }
      const close = document.createElement('span');
      close.className = 'tab-close';
      close.textContent = '\u00d7';
      close.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          await rpc('destroy_session', { sessionId: s.sessionId });
          await refreshSessions();
        } catch (_) {}
      });
      tab.appendChild(close);
      tab.addEventListener('click', () => selectSession(s, tab));
      sessionTabBar.insertBefore(tab, addBtn);
      if (s.isDefault) {
        activeSessionId = s.sessionId;
        threadTitle.textContent = s.label || s.sessionId;
      }
    });
  } catch (_) {}
}

function selectSession(s, clickedEl) {
  activeSessionId = s.sessionId;
  threadTitle.textContent = s.label || s.sessionId;
  document.querySelectorAll('.session-tab').forEach(el => el.classList.remove('active'));
  if (clickedEl) clickedEl.classList.add('active');
  rpc('switch_session', { session_id: s.sessionId }).then(() => refreshStatusBar()).catch(() => {});
}

// status bar + workspace bar
async function refreshStatusBar() {
  try {
    const status = await rpc('get_status_view', {});
    if (status) {
      sbCwd.textContent = status.workingDirectory || status.cwd || 'Local';
      sbPermission.textContent = status.permissionMode || status.sandbox?.preset || '--';
      sbGit.textContent = status.gitBranch ? `\u2387 ${status.gitBranch}` : '--';
      // workspace bar
      const cwd = status.workingDirectory || status.cwd || '';
      const name = cwd.split('/').filter(Boolean).pop() || 'Project';
      projectAvatar.textContent = name.charAt(0).toUpperCase();
      projectName.textContent = name;
      projectPath.textContent = cwd;
      wbGitBranch.textContent = status.gitBranch || '--';
      wbPermission.textContent = status.permissionMode || status.sandbox?.preset || '--';
      // file changes
      const changes = status.fileChanges || status.changes;
      if (changes && changes.filesChanged) {
        wbFileChanges.hidden = false;
        wbFcCount.textContent = changes.filesChanged;
        wbFcAdded.textContent = `+${changes.additions || 0}`;
        wbFcRemoved.textContent = `-${changes.deletions || 0}`;
        updateFileChanges(status);
      } else {
        wbFileChanges.hidden = true;
      }
    }
  } catch (_) {}
}

function showSpinner(v) { sbSpinner.hidden = !v; }

// activity + file changes
async function renderActivity() {
  try {
    const status = await rpc('get_status_view', {});
    if (!status) return;
    const mutations = status.lastMutations || status.mutations || [];
    if (mutations.length) {
      const ind = document.createElement('div');
      ind.className = 'activity-indicator';
      ind.textContent = `${mutations.length} file(s) modified`;
      chatMessages.appendChild(ind);
    }
    const changes = status.fileChanges || status.changes;
    if (changes && changes.filesChanged) {
      const bar = document.createElement('div');
      bar.className = 'file-changes-bar';
      bar.innerHTML = `${changes.filesChanged} files changed <span class="added">+${changes.additions || 0}</span> <span class="removed">-${changes.deletions || 0}</span> <span class="review-link">Review changes &nearr;</span>`;
      bar.querySelector('.review-link').addEventListener('click', openFileChangesPanel);
      chatMessages.appendChild(bar);
      sbChanges.hidden = false;
      sbChanges.innerHTML = `${changes.filesChanged} files <span class="added">+${changes.additions || 0}</span> <span class="removed">-${changes.deletions || 0}</span>`;
    }
  } catch (_) {}
}

// send message
async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  clearWelcome();
  addMessage(text, 'user');
  chatInput.value = '';
  chatInput.focus();
  await ensureInitialized();
  const pending = addMessage('thinking...', 'assistant');
  showSpinner(true);
  try {
    const result = await rpc('send_chat', { message: text });
    let content;
    if (typeof result === 'string') content = result;
    else if (result.content) content = result.content;
    else if (result.text) content = result.text;
    else if (result.message) content = result.message;
    else content = '```json\n' + JSON.stringify(result, null, 2) + '\n```'; // pretty-print fallback
    pending.innerHTML = renderMarkdown(content);
    await renderActivity();
  } catch (e) {
    pending.textContent = `Error: ${e}`;
    pending.style.color = 'var(--error)';
  }
  showSpinner(false);
}

// event listeners
sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
providerSelect.addEventListener('change', async () => {
  const prev = activeProvider;
  try {
    await rpc('switch_provider', { provider: providerSelect.value });
    await refreshProviderInfo();
  } catch (e) {
    providerInfo.textContent = `Switch failed: ${e}`;
    providerInfo.style.color = 'var(--error)';
    if (prev) providerSelect.value = prev; // revert dropdown
  }
});
// session tab bar
sessionTabAdd.addEventListener('click', () => {
  newSessionModal.hidden = false;
  newSessionNameInput.value = '';
  newSessionNameInput.focus();
});
modalCancel.addEventListener('click', () => { newSessionModal.hidden = true; });
modalCreate.addEventListener('click', async () => {
  const label = newSessionNameInput.value.trim() || `session-${Date.now()}`;
  newSessionModal.hidden = true;
  await ensureInitialized();
  try {
    await rpc('create_session', { label });
    await refreshSessions();
    await refreshHistorySidebar();
  } catch (e) {
    addMessage(`Failed to create session: ${e}`, 'assistant').style.color = 'var(--error)';
  }
});
newSessionModal.addEventListener('click', (e) => { if (e.target === newSessionModal) newSessionModal.hidden = true; });
// file changes panel toggle
wbFileChanges.addEventListener('click', toggleFileChangesPanel);
// collab panel toggle
document.getElementById('wb-collab').addEventListener('click', toggleCollabPanel);


// thread menu
threadMenuBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  threadMenu.hidden = !threadMenu.hidden;
});
document.addEventListener('click', () => { threadMenu.hidden = true; });
threadMenu.querySelectorAll('.thread-menu-item').forEach(item => {
  item.addEventListener('click', async () => {
    threadMenu.hidden = true;
    if (!activeSessionId) return;
    if (item.dataset.action === 'rename') {
      const name = prompt('Rename session:', threadTitle.textContent);
      if (name) {
        try {
          await rpc('rename_session', { sessionId: activeSessionId, label: name });
          threadTitle.textContent = name;
          await refreshSessions();
        } catch (_) {}
      }
    } else if (item.dataset.action === 'delete') {
      try {
        await rpc('destroy_session', { sessionId: activeSessionId });
        activeSessionId = null;
        threadTitle.textContent = 'New thread';
        await refreshSessions();
      } catch (_) {}
    }
  });
});

// register views
registerView('chat', () => {});
registerView('settings', initSettings);
registerView('skills', initSkills);
registerView('automations', () => {
  import('./skills.js').then(m => m.initAutomations());
});
registerView('history', initHistory);

// sidebar nav
document.querySelectorAll('.sidebar-nav-item').forEach(el => {
  el.addEventListener('click', () => showView(el.dataset.nav));
});
settingsBack.addEventListener('click', () => showView('chat'));

// status polling
setInterval(refreshStatusBar, 10000);

// auto-save on unload
window.addEventListener('beforeunload', () => {
  cleanupCollab();
  if (initialized) rpc('save_session', {}).catch(() => {});
});

// auto-init
applyCustomFonts();
initFileChangesPanel();
initCollabPanel();
initAutocomplete();
ensureInitialized();
