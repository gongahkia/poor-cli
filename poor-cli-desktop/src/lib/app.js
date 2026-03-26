// poor-cli desktop — frontend app logic
import { rpc } from './rpc.js';
import { registerView, showView } from './views.js';

const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const providerSelect = document.getElementById('provider-select');
const providerInfo = document.getElementById('provider-info');
const sessionList = document.getElementById('session-list');
const newSessionBtn = document.getElementById('new-session-btn');

let initialized = false;

export function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message message-${role}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function clearWelcome() {
  const welcome = chatMessages.querySelector('.welcome-message');
  if (welcome) welcome.remove();
}

async function ensureInitialized() {
  if (initialized) return;
  try {
    await rpc('initialize_backend', {});
    initialized = true;
    await refreshProviderInfo();
    await refreshSessions();
  } catch (e) {
    providerInfo.textContent = `Error: ${e}`;
  }
}

async function refreshProviderInfo() {
  try {
    const info = await rpc('get_provider_info', {});
    providerInfo.textContent = `${info.name || 'unknown'} / ${info.model || 'unknown'}`;
  } catch (_) {}
}

export async function refreshSessions() {
  try {
    const result = await rpc('list_sessions', {});
    const sessions = result.sessions || [];
    sessionList.innerHTML = '';
    sessions.forEach(s => {
      const div = document.createElement('div');
      div.className = `session-item${s.isDefault ? ' active' : ''}`;
      div.textContent = s.label || s.sessionId;
      sessionList.appendChild(div);
    });
  } catch (_) {}
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  clearWelcome();
  addMessage(text, 'user');
  chatInput.value = '';
  chatInput.focus();
  await ensureInitialized();
  const pending = addMessage('thinking...', 'assistant');
  try {
    const result = await rpc('send_chat', { message: text });
    const content = result.content || result.text || JSON.stringify(result);
    pending.textContent = content;
  } catch (e) {
    pending.textContent = `Error: ${e}`;
    pending.style.color = 'var(--error)';
  }
}

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

providerSelect.addEventListener('change', async () => {
  try {
    await rpc('switch_provider', { provider: providerSelect.value });
    await refreshProviderInfo();
  } catch (_) {}
});

newSessionBtn.addEventListener('click', async () => {
  try {
    await rpc('create_session', { label: `session-${Date.now()}` });
    await refreshSessions();
  } catch (_) {}
});

// register chat as default view
registerView('chat', () => {});

// sidebar nav click handler
document.querySelectorAll('.sidebar-nav-item').forEach(el => {
  el.addEventListener('click', () => showView(el.dataset.nav));
});

// auto-init
ensureInitialized();
