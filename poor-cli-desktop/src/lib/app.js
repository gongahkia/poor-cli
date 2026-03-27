// poor-cli desktop — frontend app logic
import { rpc } from './rpc.js';
import { registerView, showView } from './views.js';
import { renderMarkdown } from './markdown.js';
import { initSettings } from './settings.js';
import { initSkills } from './skills.js';
import { initHistory, refreshHistorySidebar } from './history.js';

const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const providerSelect = document.getElementById('provider-select');
const providerInfo = document.getElementById('provider-info');
const sessionList = document.getElementById('session-list');
const newSessionBtn = document.getElementById('new-session-btn');
const modelSelector = document.getElementById('model-selector'); // removed
const effortToggle = document.getElementById('effort-toggle'); // removed
const threadTitle = document.getElementById('thread-title');
const threadMenuBtn = document.getElementById('thread-menu-btn');
const threadMenu = document.getElementById('thread-menu');
const accountBtn = document.getElementById('account-btn'); // removed from DOM
const accountMenu = document.getElementById('account-menu');
const settingsBack = document.getElementById('settings-back');
const sbCwd = document.getElementById('sb-cwd');
const sbPermission = document.getElementById('sb-permission');
const sbGit = document.getElementById('sb-git');
const sbSpinner = document.getElementById('sb-spinner');
const sbChanges = document.getElementById('sb-changes');

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
    await Promise.all([refreshProviderInfo(), refreshSessions(), populateModels(), refreshStatusBar(), refreshHistorySidebar()]);
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
async function refreshProviderInfo() {
  try {
    const info = await rpc('get_provider_info', {});
    providerInfo.textContent = `${info.name || 'unknown'} / ${info.model || 'unknown'}`;
  } catch (_) {}
}

// models
async function populateModels() {
  if (!modelSelector) return;
  try {
    const result = await rpc('list_providers', {});
    const providers = result.providers || result;
    modelSelector.innerHTML = '<option value="">Auto</option>';
    if (typeof providers === 'object') {
      for (const [name, data] of Object.entries(providers)) {
        const group = document.createElement('optgroup');
        group.label = name;
        const models = data.models || data.available_models || [];
        models.forEach(m => {
          const opt = document.createElement('option');
          opt.value = `${name}:${m}`;
          opt.textContent = m;
          group.appendChild(opt);
        });
        if (group.children.length) modelSelector.appendChild(group);
      }
    }
  } catch (_) {}
}

// sessions
export async function refreshSessions() {
  try {
    const result = await rpc('list_sessions', {});
    const sessions = result.sessions || [];
    sessionList.innerHTML = '';
    sessions.forEach(s => {
      const div = document.createElement('div');
      div.className = `session-item${s.isDefault ? ' active' : ''}`;
      const label = document.createElement('span');
      label.textContent = s.label || s.sessionId;
      div.appendChild(label);
      const ts = document.createElement('span');
      ts.className = 'timestamp';
      ts.textContent = relativeTime(s.createdAt);
      div.appendChild(ts);
      div.addEventListener('click', (e) => selectSession(s, e.currentTarget));
      sessionList.appendChild(div);
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
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  if (clickedEl) clickedEl.classList.add('active');
}

// status bar
async function refreshStatusBar() {
  try {
    const status = await rpc('get_status_view', {});
    if (status) {
      sbCwd.textContent = status.workingDirectory || status.cwd || 'Local';
      sbPermission.textContent = status.permissionMode || status.sandbox?.preset || '--';
      sbGit.textContent = status.gitBranch ? `\u2387 ${status.gitBranch}` : '--';
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
    const content = result.content || result.text || JSON.stringify(result);
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
  try {
    await rpc('switch_provider', { provider: providerSelect.value });
    await refreshProviderInfo();
  } catch (_) {}
});
if (modelSelector) modelSelector.addEventListener('change', async () => {
  const val = modelSelector.value;
  if (!val) return;
  const [provider, ...modelParts] = val.split(':');
  try {
    await rpc('switch_provider', { provider, model: modelParts.join(':') });
    await refreshProviderInfo();
  } catch (_) {}
});
newSessionBtn.addEventListener('click', async () => {
  try {
    await rpc('create_session', { label: `session-${Date.now()}` });
    await refreshSessions();
    await refreshHistorySidebar();
  } catch (_) {}
});


// thread menu
threadMenuBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  threadMenu.hidden = !threadMenu.hidden;
});
document.addEventListener('click', () => { threadMenu.hidden = true; if (accountMenu) accountMenu.hidden = true; });
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

// account menu (removed from DOM — guarded)
if (accountBtn && accountMenu) {
  accountBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    accountMenu.hidden = !accountMenu.hidden;
  });
  const settingsAction = accountMenu.querySelector('[data-action="settings"]');
  if (settingsAction) settingsAction.addEventListener('click', () => {
    accountMenu.hidden = true;
    showView('settings');
  });
}


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
  if (initialized) rpc('save_session', {}).catch(() => {});
});

// auto-init
ensureInitialized();
