import { S, fn } from './state.js';
let panelEl, messagesEl, inputEl, sendBtn, statusEl, providerSel;
let settingsEl, settingsBtn, keyProviderSel, keyInput, keySaveBtn, keyStatusEl;
let history = [];
const STORAGE_KEY = 'haus_api_keys';
export function initChat() {
  fn.toggleChat = toggleChat;
  panelEl = document.getElementById('chat-panel');
  messagesEl = document.getElementById('chat-messages');
  inputEl = document.getElementById('chat-input');
  sendBtn = document.getElementById('chat-send');
  statusEl = document.getElementById('chat-status');
  providerSel = document.getElementById('chat-provider');
  settingsEl = document.getElementById('chat-settings');
  settingsBtn = document.getElementById('chat-settings-btn');
  keyProviderSel = document.getElementById('chat-key-provider');
  keyInput = document.getElementById('chat-key-input');
  keySaveBtn = document.getElementById('chat-key-save');
  keyStatusEl = document.getElementById('chat-key-status');
  document.getElementById('chat-btn').addEventListener('click', toggleChat);
  sendBtn.addEventListener('click', send);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  settingsBtn.addEventListener('click', () => {
    const open = settingsEl.style.display !== 'none';
    settingsEl.style.display = open ? 'none' : '';
    if (!open) loadKeyField();
  });
  keyProviderSel.addEventListener('change', loadKeyField);
  keySaveBtn.addEventListener('click', saveKey);
  refreshProviders();
}
function getKeys() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; }
}
function setKeys(keys) { localStorage.setItem(STORAGE_KEY, JSON.stringify(keys)); }
function loadKeyField() {
  const keys = getKeys();
  const p = keyProviderSel.value;
  keyInput.value = keys[p] || '';
  keyStatusEl.textContent = keys[p] ? 'Key saved' : '';
}
function saveKey() {
  const keys = getKeys();
  const p = keyProviderSel.value;
  const v = keyInput.value.trim();
  if (v) { keys[p] = v; } else { delete keys[p]; }
  setKeys(keys);
  keyStatusEl.textContent = v ? 'Saved' : 'Removed';
  refreshProviders();
}
function refreshProviders() {
  const keys = getKeys();
  const available = Object.keys(keys).filter(k => keys[k]);
  providerSel.innerHTML = '';
  for (const p of available) {
    const opt = document.createElement('option');
    opt.value = p; opt.textContent = p;
    providerSel.appendChild(opt);
  }
  providerSel.style.display = available.length > 1 ? '' : 'none';
  if (available.length > 0) {
    statusEl.textContent = '';
    statusEl.style.display = 'none';
  } else {
    statusEl.textContent = 'Click \u2699 to add an API key (Anthropic, OpenAI, or Gemini)';
    statusEl.style.display = '';
  }
}
function toggleChat() {
  panelEl.classList.toggle('open');
  if (panelEl.classList.contains('open')) inputEl.focus();
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
  if (!text) return;
  const keys = getKeys();
  const provider = providerSel.value;
  const apiKey = keys[provider];
  if (!provider || !apiKey) {
    appendMessage('error', 'No API key configured. Click \u2699 to add one.');
    return;
  }
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
      body: JSON.stringify({ message: text, history, provider, api_key: apiKey }),
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
