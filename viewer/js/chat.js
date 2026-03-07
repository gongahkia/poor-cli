import { S, fn } from './state.js';
let panelEl, messagesEl, inputEl, sendBtn, statusEl, providerSel;
let history = [];
let available = false;
let providers = [];
export function initChat() {
  fn.toggleChat = toggleChat;
  panelEl = document.getElementById('chat-panel');
  messagesEl = document.getElementById('chat-messages');
  inputEl = document.getElementById('chat-input');
  sendBtn = document.getElementById('chat-send');
  statusEl = document.getElementById('chat-status');
  providerSel = document.getElementById('chat-provider');
  document.getElementById('chat-btn').addEventListener('click', toggleChat);
  sendBtn.addEventListener('click', send);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  checkStatus();
}
function toggleChat() {
  panelEl.classList.toggle('open');
  if (panelEl.classList.contains('open')) inputEl.focus();
}
async function checkStatus() {
  try {
    const res = await fetch('/api/chat/status');
    const data = await res.json();
    available = data.available;
    providers = data.providers || [];
    if (available) {
      statusEl.textContent = '';
      statusEl.style.display = 'none';
      providerSel.innerHTML = '';
      for (const p of providers) {
        const opt = document.createElement('option');
        opt.value = p; opt.textContent = p;
        providerSel.appendChild(opt);
      }
      providerSel.style.display = providers.length > 1 ? '' : 'none';
    } else {
      statusEl.textContent = data.reason || 'Chat unavailable';
      statusEl.style.display = '';
      inputEl.disabled = true;
      sendBtn.disabled = true;
    }
  } catch { statusEl.textContent = 'Chat server not reachable'; statusEl.style.display = ''; }
}
function appendMessage(role, text) {
  const div = document.createElement('div');
  div.className = 'chat-msg chat-' + role;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
async function send() {
  const text = inputEl.value.trim();
  if (!text || !available) return;
  inputEl.value = '';
  appendMessage('user', text);
  inputEl.disabled = true;
  sendBtn.disabled = true;
  const loading = document.createElement('div');
  loading.className = 'chat-msg chat-loading';
  loading.textContent = 'Thinking...';
  messagesEl.appendChild(loading);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history, provider: providerSel.value }),
    });
    const data = await res.json();
    loading.remove();
    if (data.error) { appendMessage('error', data.error); }
    else {
      appendMessage('assistant', data.response);
      history = data.history || [];
    }
  } catch (e) { loading.remove(); appendMessage('error', 'Request failed: ' + e.message); }
  inputEl.disabled = false;
  sendBtn.disabled = false;
  inputEl.focus();
}
