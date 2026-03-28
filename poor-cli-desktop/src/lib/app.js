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
import { initTasks } from './tasks.js';
import { initCheckpoints } from './checkpoints.js';
import { initCommands } from './commands.js';
import { initWorkflows } from './workflows.js';
import { initTools } from './tools.js';
import { initDiagnostics } from './diagnostics.js';
import { initContext } from './context.js';
import { initGit } from './git.js';
import { initPalette } from './palette.js';

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

// provider + model
let activeProvider = null;
const modelSelect = document.getElementById('model-select');
let providerModels = {}; // provider -> [models]

async function refreshProviderInfo() {
  try {
    const info = await rpc('get_provider_info', {});
    const name = info.name || 'unknown';
    const model = info.model || 'unknown';
    providerInfo.textContent = `${name} / ${model}`;
    activeProvider = name;
    providerSelect.value = name;
    await refreshModelList(name, model);
  } catch (e) {
    providerInfo.textContent = 'Not connected';
  }
}

async function refreshModelList(provider, currentModel) {
  if (!providerModels[provider]) {
    try {
      const result = await rpc('list_providers', {});
      for (const [name, info] of Object.entries(result || {})) {
        providerModels[name] = info.models || [];
      }
    } catch (_) {}
  }
  const models = providerModels[provider] || [];
  modelSelect.innerHTML = '';
  if (!models.length) {
    modelSelect.innerHTML = '<option value="">default</option>';
  } else {
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      if (m === currentModel) opt.selected = true;
      modelSelect.appendChild(opt);
    });
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

// slash command dispatch — maps /commands to RPC calls
const SLASH_HANDLERS = {
  '/help': async () => ({ content: 'Available commands: /help, /status, /plan, /history, /cost, /review, /test, /debug, /implement, /summarize, /qa, /diff, /checkpoint, /checkpoints, /undo, /context, /compact, /sandbox, /provider, /config, /settings, /api-key, /theme, /tools, /mcp, /files, /add, /drop, /focus, /workspace-map, /skills, /commands, /autopilot, /task, /doctor, /run, /commit, /collab, /economy, /export, /gc\n\nType `/` to see the full list with descriptions.' }),
  '/status': () => rpc('get_status_view', {}),
  '/cost': () => rpc('get_session_cost', {}),
  '/history': async () => { showView('history'); return { content: 'Opened history view.' }; },
  '/provider': () => rpc('get_provider_info', {}),
  '/config': () => rpc('get_config', {}),
  '/settings': async () => { showView('settings'); return { content: 'Opened settings.' }; },
  '/tools': () => rpc('get_tools', {}),
  '/skills': async () => { showView('skills'); return { content: 'Opened skills view.' }; },
  '/files': () => rpc('get_status_view', {}),
  '/checkpoint': async (args) => rpc('create_checkpoint', { description: args || 'Manual checkpoint' }),
  '/checkpoints': async () => { showView('checkpoints'); return { content: 'Opened checkpoints view.' }; },
  '/undo': async () => rpc('restore_checkpoint', { checkpoint_id: 'last' }),
  '/task': async () => { showView('tasks'); return { content: 'Opened tasks view.' }; },
  '/commands': async () => { showView('commands'); return { content: 'Opened commands view.' }; },
  '/clear': async () => { await rpc('clear_history', {}); return { content: 'Conversation history cleared.' }; },
  '/new-session': async () => {
    const label = `session-${Date.now()}`;
    await rpc('create_session', { label });
    await refreshSessions();
    return { content: `Created session: ${label}` };
  },
  '/mcp': () => rpc('get_mcp_status', {}),
  '/doctor': () => rpc('get_doctor_report', {}),
  '/context': async () => { showView('context'); return { content: 'Opened context view.' }; },
  '/compact': async () => rpc('send_chat', { message: '/compact' }),
  '/economy': () => rpc('get_session_cost', {}),
  '/export': async () => { document.getElementById('export-modal').hidden = false; return { content: 'Select export format.' }; },
  // workflow shortcuts — send to AI as chat messages
  '/review': async () => rpc('send_chat', { message: '/review' }),
  '/test': async () => rpc('send_chat', { message: '/test' }),
  '/debug': async () => rpc('send_chat', { message: '/debug' }),
  '/implement': async () => rpc('send_chat', { message: '/implement' }),
  '/summarize': async () => rpc('send_chat', { message: '/summarize' }),
  '/qa': async () => rpc('send_chat', { message: '/qa' }),
  // pass-through to AI
  '/plan': async () => rpc('send_chat', { message: '/plan' }),
  '/diff': async () => { toggleFileChangesPanel(); return { content: 'Opened file changes panel.' }; },
  '/commit': async () => rpc('send_chat', { message: '/commit' }),
  '/gc': async () => rpc('send_chat', { message: '/gc' }),
};
async function handleSlashCommand(text) {
  const parts = text.split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const args = parts.slice(1).join(' ');
  // exact match handler
  if (SLASH_HANDLERS[cmd]) return SLASH_HANDLERS[cmd](args);
  // commands with args that map to RPC
  if (cmd === '/switch' || cmd === '/provider' && args.startsWith('switch')) {
    const model = args.replace('switch', '').trim();
    return rpc('switch_provider', { provider: model || 'gemini' });
  }
  if (cmd === '/api-key') return rpc('get_api_key_status', {});
  if (cmd === '/search' && args) return rpc('search_history', { term: args });
  if (cmd === '/run' && args) return rpc('send_chat', { message: `!${args}` });
  if (cmd === '/add' && args) return { content: `Context file hint: use @${args} in your next message to attach it.` };
  if (cmd === '/sandbox') return rpc('get_sandbox_status', {});
  if (cmd === '/theme') {
    showView('settings');
    return { content: 'Opened settings. Use the General section to change theme.' };
  }
  if (cmd === '/focus' && args) return rpc('send_chat', { message: `/focus ${args}` });
  if (cmd === '/resume') return rpc('send_chat', { message: '/resume' });
  if (cmd === '/autopilot') return rpc('send_chat', { message: '/autopilot' });
  if (cmd === '/fix-failures') return rpc('send_chat', { message: '/fix-failures' });
  if (cmd === '/timeline') return rpc('send_chat', { message: '/timeline' });
  if (cmd === '/workspace-map') return rpc('send_chat', { message: '/workspace-map' });
  if (cmd === '/read' && args) return rpc('send_chat', { message: `/read ${args}` });
  if (cmd === '/collab') { document.getElementById('wb-collab').click(); return { content: 'Toggled collaboration panel.' }; }
  if (cmd === '/pass') return rpc('next_driver', {});
  if (cmd === '/suggest' && args) return rpc('suggest_text', { text: args });
  if (cmd === '/retry') return rpc('send_chat', { message: '/retry' });
  if (cmd === '/drop' && args) return rpc('send_chat', { message: `/drop ${args}` });
  if (cmd === '/image') return { content: 'Attach an image by dragging it into the chat or using @filename.' };
  if (cmd === '/save-prompt' && args) return rpc('send_chat', { message: `/save-prompt ${args}` });
  if (cmd === '/use' && args) return rpc('send_chat', { message: `/use ${args}` });
  if (cmd === '/setup') return rpc('send_chat', { message: '/setup' });
  if (cmd === '/profile' && args) return rpc('send_chat', { message: `/profile ${args}` });
  if (cmd === '/watch' && args) return rpc('send_chat', { message: `/watch ${args}` });
  // fallback: send to AI as a normal message (the AI can interpret some commands contextually)
  return null;
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
  // try slash command dispatch first
  if (text.startsWith('/')) {
    const pending = addMessage('...', 'assistant');
    showSpinner(true);
    try {
      const slashResult = await handleSlashCommand(text);
      if (slashResult !== null) {
        let content;
        if (typeof slashResult === 'string') content = slashResult;
        else if (slashResult.content) content = slashResult.content;
        else if (slashResult.text) content = slashResult.text;
        else content = '```json\n' + JSON.stringify(slashResult, null, 2) + '\n```';
        pending.innerHTML = renderMarkdown(content);
        showSpinner(false);
        return;
      }
    } catch (e) {
      pending.textContent = `Command error: ${e}`;
      pending.style.color = 'var(--error)';
      showSpinner(false);
      return;
    }
    // null means fallback to AI chat
    pending.remove();
    showSpinner(false);
  }
  const pending = addMessage('thinking...', 'assistant');
  showSpinner(true);
  try {
    const result = await rpc('send_chat', { message: text });
    let content;
    if (typeof result === 'string') content = result;
    else if (result.content) content = result.content;
    else if (result.text) content = result.text;
    else if (result.message) content = result.message;
    else content = '```json\n' + JSON.stringify(result, null, 2) + '\n```';
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
    providerModels = {}; // clear cache on provider switch
    await refreshProviderInfo();
  } catch (e) {
    providerInfo.textContent = `Switch failed: ${e}`;
    providerInfo.style.color = 'var(--error)';
    if (prev) providerSelect.value = prev;
  }
});
modelSelect.addEventListener('change', async () => {
  const model = modelSelect.value;
  if (!model) return;
  try {
    await rpc('switch_provider', { provider: providerSelect.value, model });
    await refreshProviderInfo();
  } catch (e) {
    providerInfo.textContent = `Model switch failed: ${e}`;
    providerInfo.style.color = 'var(--error)';
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
    } else if (item.dataset.action === 'export') {
      document.getElementById('export-modal').hidden = false;
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
registerView('tasks', initTasks);
registerView('checkpoints', initCheckpoints);
registerView('commands', initCommands);
registerView('workflows', initWorkflows);
registerView('tools', initTools);
registerView('diagnostics', initDiagnostics);
registerView('context', initContext);
registerView('git', initGit);

// sidebar nav
document.querySelectorAll('.sidebar-nav-item').forEach(el => {
  el.addEventListener('click', () => showView(el.dataset.nav));
});
settingsBack.addEventListener('click', () => showView('chat'));

// routing mode
const routingSelect = document.getElementById('routing-mode');
routingSelect.addEventListener('change', async () => {
  try {
    await rpc('set_config', { keyPath: 'model.routing_mode', value: routingSelect.value });
    await refreshProviderInfo();
  } catch (e) { providerInfo.textContent = `Routing error: ${e}`; }
});

// cost display
const sbCostEl = document.getElementById('sb-cost');
async function refreshCost() {
  try {
    const cost = await rpc('get_session_cost', {});
    if (cost) {
      const tokens = cost.totalTokens || cost.tokens || 0;
      const usd = cost.estimatedCost || cost.cost || 0;
      if (tokens > 0 || usd > 0) {
        sbCostEl.hidden = false;
        sbCostEl.textContent = usd > 0 ? `$${usd.toFixed(4)} (${tokens} tok)` : `${tokens} tok`;
      } else { sbCostEl.hidden = true; }
    }
  } catch (_) { sbCostEl.hidden = true; }
}

// export handlers
document.getElementById('export-modal-cancel').addEventListener('click', () => { document.getElementById('export-modal').hidden = true; });
document.getElementById('export-modal-go').addEventListener('click', async () => {
  const format = document.getElementById('export-format').value;
  document.getElementById('export-modal').hidden = true;
  try {
    const result = await rpc('export_conversation', { format });
    const content = result.content || result.text || JSON.stringify(result, null, 2);
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `conversation.${format === 'json' ? 'json' : format === 'markdown' ? 'md' : 'txt'}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) { addMessage(`Export failed: ${e}`, 'assistant'); }
});

// status polling
setInterval(() => { refreshStatusBar(); refreshCost(); }, 10000);

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
initPalette();
ensureInitialized();
