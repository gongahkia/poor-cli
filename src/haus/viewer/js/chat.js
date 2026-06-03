import { fn } from './state.js';

let panelEl;
let messagesEl;
let inputEl;
let sendBtn;
let statusEl;
let providerSel;
let modelInput;
let clearBtn;

let settingsEl;
let settingsBtn;
let keyProviderSel;
let keyInput;
let keySaveBtn;
let keyStatusEl;

let history = [];
let serverStatus = null;
let sending = false;

const KEYS_STORAGE = 'haus_api_keys';
const PROVIDER_STORAGE = 'haus_chat_provider';
const MODEL_STORAGE = 'haus_chat_model';
const HISTORY_STORAGE = 'haus_chat_history';
const TRANSCRIPT_STORAGE = 'haus_chat_transcript';

export function initChat() {
  fn.toggleChat = toggleChat;

  panelEl = document.getElementById('chat-panel');
  messagesEl = document.getElementById('chat-messages');
  inputEl = document.getElementById('chat-input');
  sendBtn = document.getElementById('chat-send');
  statusEl = document.getElementById('chat-status');
  providerSel = document.getElementById('chat-provider');
  modelInput = document.getElementById('chat-model');
  clearBtn = document.getElementById('chat-clear-btn');

  settingsEl = document.getElementById('chat-settings');
  settingsBtn = document.getElementById('chat-settings-btn');
  keyProviderSel = document.getElementById('chat-key-provider');
  keyInput = document.getElementById('chat-key-input');
  keySaveBtn = document.getElementById('chat-key-save');
  keyStatusEl = document.getElementById('chat-key-status');

  document.getElementById('chat-btn').addEventListener('click', toggleChat);
  sendBtn.addEventListener('click', () => send());

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  modelInput.addEventListener('change', () => {
    localStorage.setItem(MODEL_STORAGE, modelInput.value.trim());
  });

  providerSel.addEventListener('change', () => {
    localStorage.setItem(PROVIDER_STORAGE, providerSel.value);
    hydrateModelPlaceholder();
  });

  clearBtn.addEventListener('click', clearConversation);

  settingsBtn.addEventListener('click', () => {
    const open = settingsEl.style.display !== 'none';
    settingsEl.style.display = open ? 'none' : '';
    if (!open) loadKeyField();
  });

  keyProviderSel.addEventListener('change', loadKeyField);
  keySaveBtn.addEventListener('click', saveKey);

  for (const chip of document.querySelectorAll('.chat-chip')) {
    chip.addEventListener('click', () => {
      inputEl.value = chip.textContent || '';
      inputEl.focus();
    });
  }

  history = loadJson(HISTORY_STORAGE, []);
  renderTranscript();

  const storedModel = localStorage.getItem(MODEL_STORAGE);
  if (storedModel) modelInput.value = storedModel;

  refreshProviders();
  fetchStatus();
}

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function getKeys() {
  return loadJson(KEYS_STORAGE, {});
}

function setKeys(keys) {
  saveJson(KEYS_STORAGE, keys);
}

function loadKeyField() {
  const keys = getKeys();
  const provider = keyProviderSel.value;
  keyInput.value = keys[provider] || '';
  keyStatusEl.textContent = keys[provider] ? 'Key loaded from browser storage' : '';
}

function saveKey() {
  const keys = getKeys();
  const provider = keyProviderSel.value;
  const value = keyInput.value.trim();

  if (value) keys[provider] = value;
  else delete keys[provider];

  setKeys(keys);
  keyStatusEl.textContent = value ? 'Saved' : 'Removed';
  refreshProviders();
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/chat/status');
    if (!res.ok) throw new Error(`status ${res.status}`);
    serverStatus = await res.json();
    refreshProviders();
  } catch (err) {
    console.warn('chat status unavailable', err);
    setStatus('Chat backend status unavailable. You can still try sending messages.', true);
  }
}

function refreshProviders() {
  const keys = getKeys();
  const providersFromServer = Array.isArray(serverStatus?.supported_providers)
    ? serverStatus.supported_providers
    : ['anthropic', 'openai', 'gemini'];

  const availableProviders = providersFromServer.filter((p) => keys[p]);
  providerSel.innerHTML = '';

  for (const provider of availableProviders) {
    const opt = document.createElement('option');
    opt.value = provider;
    opt.textContent = provider;
    providerSel.appendChild(opt);
  }

  const storedProvider = localStorage.getItem(PROVIDER_STORAGE);
  if (storedProvider && availableProviders.includes(storedProvider)) {
    providerSel.value = storedProvider;
  } else if (availableProviders.length > 0) {
    providerSel.value = availableProviders[0];
    localStorage.setItem(PROVIDER_STORAGE, providerSel.value);
  }

  if (availableProviders.length === 0) {
    providerSel.style.display = 'none';
    setStatus('Open Settings and add an API key (Anthropic, OpenAI, or Gemini).', true);
  } else {
    providerSel.style.display = '';
    setStatus('');
  }

  hydrateModelPlaceholder();
}

function hydrateModelPlaceholder() {
  const provider = providerSel.value;
  const defaults = serverStatus?.default_models || {};
  const model = defaults[provider] || 'provider default model';
  modelInput.placeholder = `Auto (${model})`;
}

function toggleChat() {
  panelEl.classList.toggle('open');
  if (panelEl.classList.contains('open')) inputEl.focus();
}

function setStatus(text, isError = false) {
  if (!text) {
    statusEl.textContent = '';
    statusEl.style.display = 'none';
    return;
  }

  statusEl.textContent = text;
  statusEl.style.display = '';
  statusEl.style.color = isError ? '#a66' : '#8a8';
}

function appendMessage(role, text) {
  const div = document.createElement('div');
  div.className = `chat-msg chat-${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendTool(action) {
  maybeShowSightlineOverlay(action);
  const args = action.args && Object.keys(action.args).length > 0 ? ` ${JSON.stringify(action.args)}` : '';
  const elapsed = action.elapsed_ms !== undefined ? ` (${action.elapsed_ms}ms)` : '';
  appendMessage('tool', `${action.tool}${args} -> ${action.result}${elapsed}`);
}

function parseSightlineBlockers(action) {
  if (action.tool !== 'check_sightline') return [];
  const text = String(action.result || '');
  const args = action.args || {};
  const from = Number(args.index_from);
  const to = Number(args.index_to);

  const values = [];
  const matches = text.matchAll(/\[(\d+)\]/g);
  for (const match of matches) {
    const idx = Number(match[1]);
    if (!Number.isFinite(idx)) continue;
    if (idx === from || idx === to) continue;
    values.push(idx);
  }
  return [...new Set(values)];
}

function maybeShowSightlineOverlay(action) {
  if (action.tool !== 'check_sightline' || !fn.showSightlineOverlay) return;
  const args = action.args || {};
  fn.showSightlineOverlay({
    indexFrom: args.index_from,
    indexTo: args.index_to,
    blockerIndices: parseSightlineBlockers(action),
  });
}

function persistTranscript(role, text) {
  const transcript = loadJson(TRANSCRIPT_STORAGE, []);
  transcript.push({ role, text });
  saveJson(TRANSCRIPT_STORAGE, transcript.slice(-250));
}

function renderTranscript() {
  messagesEl.innerHTML = '';
  const transcript = loadJson(TRANSCRIPT_STORAGE, []);
  for (const msg of transcript) {
    appendMessage(msg.role || 'assistant', msg.text || '');
  }
}

function clearConversation() {
  history = [];
  saveJson(HISTORY_STORAGE, history);
  saveJson(TRANSCRIPT_STORAGE, []);
  messagesEl.innerHTML = '';
  appendMessage('assistant', 'Conversation cleared.');
  persistTranscript('assistant', 'Conversation cleared.');
}

async function send() {
  if (sending) return;

  const text = inputEl.value.trim();
  if (!text) return;

  const keys = getKeys();
  const provider = providerSel.value;
  const apiKey = keys[provider];
  if (!provider || !apiKey) {
    appendMessage('error', 'No API key configured for this provider. Open Settings to add one.');
    persistTranscript('error', 'No API key configured for this provider. Open Settings to add one.');
    return;
  }

  const model = modelInput.value.trim();

  inputEl.value = '';
  appendMessage('user', text);
  persistTranscript('user', text);

  inputEl.disabled = true;
  sendBtn.disabled = true;
  sending = true;

  const loading = document.createElement('div');
  loading.className = 'chat-msg chat-loading';
  loading.textContent = 'Planning with tools...';
  messagesEl.appendChild(loading);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history,
        provider,
        model,
        api_key: apiKey,
      }),
    });

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = { error: `Invalid JSON response (HTTP ${res.status})` };
    }

    loading.remove();

    if (!res.ok || data.error) {
      const errText = data.error || `Request failed with HTTP ${res.status}`;
      appendMessage('error', errText);
      persistTranscript('error', errText);
      return;
    }

    if (Array.isArray(data.actions) && data.actions.length > 0) {
      for (const action of data.actions) {
        appendTool(action);
        persistTranscript('tool', `${action.tool} -> ${action.result}`);
      }
    }

    const responseText = data.response || '';
    appendMessage('assistant', responseText);
    persistTranscript('assistant', responseText);

    history = Array.isArray(data.history) ? data.history : [];
    saveJson(HISTORY_STORAGE, history);

    if (data.request_id) setStatus(`Last request: ${data.request_id}`, false);
  } catch (err) {
    loading.remove();
    const textErr = `Request failed: ${err.message}`;
    appendMessage('error', textErr);
    persistTranscript('error', textErr);
  } finally {
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
    sending = false;
  }
}
