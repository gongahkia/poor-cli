import { fn } from './state.js';

let panelEl;
let messagesEl;
let inputEl;
let sendBtn;
let statusEl;
let attachmentsEl;
let attachBtn;
let imageInput;
let providerSel;
let modelInput;
let plannerModeSel;
let standardsProfileSel;
let clearBtn;

let settingsEl;
let settingsBtn;
let keyInput;
let keyPersistEl;
let keySaveBtn;
let keyForgetBtn;
let keyStatusEl;
let disableWebSearchEl;
let disableKeyStorageEl;
let providerWarningEl;

let history = [];
let serverStatus = null;
let modelCatalog = null;
let sending = false;
let pendingAttachments = [];
let sessionKeys = {};

const KEYS_STORAGE = 'haus_api_keys';
const PROVIDER_STORAGE = 'haus_chat_provider';
const MODEL_STORAGE = 'haus_chat_model';
const PLANNER_MODE_STORAGE = 'haus_chat_planner_mode';
const PROFILE_STORAGE = 'haus_chat_standards_profile';
const HISTORY_STORAGE = 'haus_chat_history';
const TRANSCRIPT_STORAGE = 'haus_chat_transcript';
const CONVERSATION_STORAGE = 'haus_chat_conversation_id';
const DISABLE_WEB_SEARCH_STORAGE = 'haus_chat_disable_web_search';
const DISABLE_KEY_STORAGE = 'haus_chat_disable_key_storage';
const DEFAULT_MAX_ATTACHMENTS = 3;
const DEFAULT_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const LOCAL_PROVIDER_IDS = new Set(['ollama', 'codex', 'gemini-cli', 'claude-code', 'opencode', 'aider', 'openai-compatible-local', 'webllm']);
const BROWSER_PROVIDER_IDS = new Set(['webllm']);
const FALLBACK_PROVIDERS = ['ollama', 'codex', 'gemini-cli', 'claude-code', 'opencode', 'aider', 'openai-compatible-local', 'webllm', 'anthropic', 'openai', 'gemini'];
let webllmEngine = null;
let webllmModel = '';
let conversationId = localStorage.getItem(CONVERSATION_STORAGE) || newConversationId();

export function initChat() {
  fn.toggleChat = toggleChat;

  panelEl = document.getElementById('chat-panel');
  messagesEl = document.getElementById('chat-messages');
  inputEl = document.getElementById('chat-input');
  sendBtn = document.getElementById('chat-send');
  statusEl = document.getElementById('chat-status');
  attachmentsEl = document.getElementById('chat-attachments');
  attachBtn = document.getElementById('chat-attach-btn');
  imageInput = document.getElementById('chat-image-input');
  providerSel = document.getElementById('chat-provider');
  modelInput = document.getElementById('chat-model');
  plannerModeSel = document.getElementById('chat-planner-mode');
  standardsProfileSel = document.getElementById('chat-standards-profile');
  clearBtn = document.getElementById('chat-clear-btn');

  settingsEl = document.getElementById('chat-settings');
  settingsBtn = document.getElementById('chat-settings-btn');
  keyInput = document.getElementById('chat-key-input');
  keyPersistEl = document.getElementById('chat-key-persist');
  keySaveBtn = document.getElementById('chat-key-save');
  keyForgetBtn = document.getElementById('chat-key-forget');
  keyStatusEl = document.getElementById('chat-key-status');
  disableWebSearchEl = document.getElementById('chat-disable-web-search');
  disableKeyStorageEl = document.getElementById('chat-disable-key-storage');
  providerWarningEl = document.getElementById('provider-data-warning');
  fn.renderJourneyPrompts = renderJourneyPrompts;

  document.getElementById('chat-btn').addEventListener('click', openChat);
  sendBtn.addEventListener('click', () => send());
  attachBtn.addEventListener('click', () => imageInput.click());
  imageInput.addEventListener('change', () => {
    addImageFiles(imageInput.files);
    imageInput.value = '';
  });

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
    loadKeyField();
    refreshProviderStatus();
    refreshProviderWarning();
  });
  plannerModeSel.addEventListener('change', () => {
    localStorage.setItem(PLANNER_MODE_STORAGE, plannerModeSel.value);
    refreshProviderWarning();
  });
  standardsProfileSel.addEventListener('change', () => {
    localStorage.setItem(PROFILE_STORAGE, standardsProfileSel.value);
  });

  clearBtn.addEventListener('click', clearConversation);
  disableWebSearchEl.checked = localStorage.getItem(DISABLE_WEB_SEARCH_STORAGE) === '1';
  disableKeyStorageEl.checked = localStorage.getItem(DISABLE_KEY_STORAGE) === '1';
  disableWebSearchEl.addEventListener('change', () => {
    localStorage.setItem(DISABLE_WEB_SEARCH_STORAGE, disableWebSearchEl.checked ? '1' : '0');
    refreshProviderWarning();
  });
  disableKeyStorageEl.addEventListener('change', () => {
    localStorage.setItem(DISABLE_KEY_STORAGE, disableKeyStorageEl.checked ? '1' : '0');
    if (disableKeyStorageEl.checked) setStoredKeys({});
    loadKeyField();
  });
  renderJourneyPrompts();

  settingsBtn.addEventListener('click', () => {
    const open = settingsEl.style.display !== 'none';
    settingsEl.style.display = open ? 'none' : '';
    if (!open) loadKeyField();
  });

  keySaveBtn.addEventListener('click', saveKey);
  keyForgetBtn.addEventListener('click', forgetKey);

  history = loadJson(historyStorageKey(), loadJson(HISTORY_STORAGE, []));
  localStorage.setItem(CONVERSATION_STORAGE, conversationId);
  renderTranscript();

  const storedModel = localStorage.getItem(MODEL_STORAGE);
  if (storedModel) modelInput.value = storedModel;
  const storedPlannerMode = localStorage.getItem(PLANNER_MODE_STORAGE);
  if (storedPlannerMode) plannerModeSel.value = storedPlannerMode;
  const storedProfile = localStorage.getItem(PROFILE_STORAGE);
  if (storedProfile) standardsProfileSel.value = storedProfile;

  refreshProviders();
  fetchStatus();
  openChat();
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

function transcriptStorageKey() {
  return fn.getProjectTranscriptKey ? fn.getProjectTranscriptKey(TRANSCRIPT_STORAGE) : TRANSCRIPT_STORAGE;
}

function historyStorageKey() {
  return fn.getProjectTranscriptKey ? fn.getProjectTranscriptKey(HISTORY_STORAGE) : HISTORY_STORAGE;
}

function saveHistory(value) {
  const trimmed = value.slice(-80);
  saveJson(historyStorageKey(), trimmed);
  saveJson(HISTORY_STORAGE, trimmed);
}

function keyStorageDisabled() {
  return Boolean(disableKeyStorageEl?.checked) || localStorage.getItem(DISABLE_KEY_STORAGE) === '1';
}

function getKeys() {
  return { ...(keyStorageDisabled() ? {} : loadJson(KEYS_STORAGE, {})), ...sessionKeys };
}

function setStoredKeys(keys) {
  saveJson(KEYS_STORAGE, keyStorageDisabled() ? {} : keys);
}

function loadKeyField() {
  const keys = getKeys();
  const storedKeys = keyStorageDisabled() ? {} : loadJson(KEYS_STORAGE, {});
  const provider = providerSel.value;
  const requiresKey = providerRequiresApiKey(provider);
  keyInput.value = keys[provider] || '';
  keyInput.disabled = !requiresKey;
  keyInput.placeholder = requiresKey ? 'sk-...' : 'No API key required';
  keyPersistEl.checked = Boolean(storedKeys[provider]) && !keyStorageDisabled();
  keyPersistEl.disabled = keyStorageDisabled() || !requiresKey;
  if (!requiresKey) keyStatusEl.textContent = localProviderStatusText(provider);
  else if (storedKeys[provider]) keyStatusEl.textContent = 'Key loaded from browser storage';
  else if (sessionKeys[provider]) keyStatusEl.textContent = 'Key available for this tab only';
  else if (keyStorageDisabled()) keyStatusEl.textContent = 'Browser key storage disabled';
  else keyStatusEl.textContent = '';
}

function saveKey() {
  const storedKeys = keyStorageDisabled() ? {} : loadJson(KEYS_STORAGE, {});
  const provider = providerSel.value;
  if (!providerRequiresApiKey(provider)) {
    keyInput.value = '';
    keyStatusEl.textContent = localProviderStatusText(provider);
    return;
  }
  const value = keyInput.value.trim();

  delete storedKeys[provider];
  delete sessionKeys[provider];

  if (value && keyPersistEl.checked && !keyStorageDisabled()) {
    storedKeys[provider] = value;
    keyStatusEl.textContent = 'Saved in this browser. Browser storage can be read by scripts on this page.';
  } else if (value) {
    sessionKeys[provider] = value;
    keyStatusEl.textContent = 'Saved for this tab only.';
  } else {
    keyStatusEl.textContent = 'Removed';
  }

  setStoredKeys(storedKeys);
  refreshProviders();
  refreshProviderStatus();
  refreshProviderWarning();
}

function forgetKey() {
  const storedKeys = loadJson(KEYS_STORAGE, {});
  const provider = providerSel.value;
  delete storedKeys[provider];
  delete sessionKeys[provider];
  setStoredKeys(storedKeys);
  keyInput.value = '';
  keyPersistEl.checked = false;
  keyStatusEl.textContent = 'Forgot key';
  refreshProviders();
  refreshProviderStatus();
  refreshProviderWarning();
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/chat/status');
    if (!res.ok) throw new Error(`status ${res.status}`);
    serverStatus = await res.json();
    await fetchModels();
    refreshProviders();
    refreshPlannerControls();
  } catch (err) {
    console.warn('chat status unavailable', err);
    setStatus('Chat backend status unavailable. You can still try sending messages.', true);
  }
}

async function fetchModels() {
  try {
    const res = await fetch('/api/chat/models');
    if (!res.ok) throw new Error(`models ${res.status}`);
    modelCatalog = await res.json();
    serverStatus = { ...(serverStatus || {}), ...modelCatalog };
  } catch (err) {
    console.warn('chat model catalog unavailable', err);
    modelCatalog = serverStatus || null;
  }
}

function refreshProviders() {
  const keys = getKeys();
  const providersFromServer = Array.isArray(serverStatus?.supported_providers)
    ? serverStatus.supported_providers
    : FALLBACK_PROVIDERS;
  const envProviders = new Set(Array.isArray(serverStatus?.providers_with_env_keys)
    ? serverStatus.providers_with_env_keys
    : []);

  providerSel.innerHTML = '';

  for (const provider of providersFromServer) {
    const opt = document.createElement('option');
    opt.value = provider;
    opt.textContent = providerLabel(provider);
    providerSel.appendChild(opt);
  }

  const storedProvider = localStorage.getItem(PROVIDER_STORAGE);
  if (storedProvider && providersFromServer.includes(storedProvider)) {
    providerSel.value = storedProvider;
  } else if (providersFromServer.length > 0) {
    providerSel.value = preferredProvider(providersFromServer, keys, envProviders);
    localStorage.setItem(PROVIDER_STORAGE, providerSel.value);
  }

  hydrateModelPlaceholder();
  loadKeyField();
  refreshProviderStatus(keys, envProviders);
}

function providerLabel(provider) {
  const spec = providerSpec(provider);
  return spec?.label || {
    anthropic: 'Anthropic',
    openai: 'OpenAI',
    gemini: 'Gemini',
    ollama: 'Ollama',
    codex: 'Codex runtime',
    'gemini-cli': 'Gemini CLI runtime',
    'claude-code': 'Claude Code runtime',
    opencode: 'opencode runtime',
    aider: 'Aider runtime',
    'openai-compatible-local': 'OpenAI-compatible local',
    webllm: 'WebLLM',
  }[provider] || provider;
}

function providerSpec(provider) {
  const providers = Array.isArray(serverStatus?.providers) ? serverStatus.providers : [];
  return providers.find((item) => item.id === provider) || null;
}

function refreshProviderStatus(keys = getKeys(), envProviders = new Set(Array.isArray(serverStatus?.providers_with_env_keys) ? serverStatus.providers_with_env_keys : [])) {
  const provider = providerSel.value;
  const spec = providerSpec(provider);
  if (!provider) setStatus('');
  else if (spec?.requires_api_key === false && spec.command_available === false) setStatus(`${providerLabel(provider)} command not found. ${spec.install_hint || 'Install or configure the runtime command.'}`, true);
  else if (spec?.requires_api_key === false) setStatus(`${providerLabel(provider)} selected. No API key required.`, false);
  else if (keys[provider] || envProviders.has(provider)) setStatus('');
  else setStatus('Deterministic planner available. Add a provider key for LLM-reviewed plans.', false);
  refreshProviderWarning();
}

function refreshProviderWarning() {
  if (!providerWarningEl) return;
  const provider = providerSel?.value || '';
  const spec = providerSpec(provider);
  const keys = getKeys();
  const hasCredential = providerHasCredential(provider, keys);
  const activeMode = hasCredential && (plannerModeSel?.value || 'auto') !== 'deterministic';
  providerWarningEl.style.display = activeMode ? '' : 'none';
  if (activeMode && spec?.requires_api_key === false) {
    providerWarningEl.textContent = spec.capabilities?.includes('text_only')
      ? 'Local runtime receives chat text and layout context only. Haus edit tools stay disabled for this provider.'
      : 'Local provider receives chat text, layout details, and attached image references on this machine.';
  } else if (activeMode) {
    providerWarningEl.textContent = disableWebSearchEl?.checked
      ? 'External LLM provider may receive chat text, layout details, and attached image references. Web search is disabled for this request.'
      : 'External LLM provider may receive chat text, layout details, attached image references, and live reference context for this request.';
  }
}

function providerRequiresApiKey(provider) {
  const spec = providerSpec(provider);
  if (!spec && LOCAL_PROVIDER_IDS.has(provider)) return false;
  return spec?.requires_api_key !== false;
}

function localProviderStatusText(provider) {
  const spec = providerSpec(provider);
  if (spec?.command_available === false) return `${providerLabel(provider)} command not found.`;
  if (spec?.capabilities?.includes('text_only')) return 'No browser key needed. Text-only local runtime.';
  return 'No browser key needed. Local provider.';
}

function preferredProvider(providers, keys, envProviders) {
  const keyed = providers.find((provider) => keys[provider] || envProviders.has(provider));
  if (keyed) return keyed;
  const localReady = providers.find((provider) => {
    const spec = providerSpec(provider);
    return spec?.requires_api_key === false && spec.command_available !== false;
  });
  if (localReady) return localReady;
  const localAny = providers.find((provider) => providerSpec(provider)?.requires_api_key === false);
  return localAny || providers[0];
}

function promptPresets(journey) {
  const sets = {
    renovation: [
      'Draft three renovation options: conservative, balanced, ambitious',
      'Validate this renovation idea before I talk to a contractor',
      'Export a homeowner-friendly renovation concept report',
    ],
    accessibility: [
      'Check the route from entry to bathroom for blockers',
      'List quick wins and renovation-level accessibility fixes',
      'Export an accessibility planning review',
    ],
    furniture_fit: [
      'Will this product fit if the room measurements are uncertain?',
      'Find smaller substitutes and explain what to measure before buying',
      'Export the shopping list and fit notes',
    ],
    designer: [
      'Turn this client intake into a pre-sales brief',
      'Prepare questions for the design call',
      'Create a client-safe presentation summary',
    ],
    blank: [
      'Start with manual room dimensions',
      'Tell me what measurements are missing',
      'Draft a concept plan for this layout',
    ],
  };
  return sets[journey] || sets.blank;
}

function renderJourneyPrompts() {
  const root = document.getElementById('chat-quick-prompts');
  if (!root) return;
  const journey = fn.getProject?.()?.journey || 'blank';
  root.innerHTML = '';
  for (const prompt of promptPresets(journey)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.prompt = prompt;
    button.textContent = prompt;
    button.addEventListener('click', () => {
      inputEl.value = prompt;
      send();
    });
    root.appendChild(button);
  }
}

function refreshPlannerControls() {
  const caps = serverStatus?.capabilities || {};
  const modes = Array.isArray(caps.planner_modes)
    ? caps.planner_modes
    : ['auto', 'deterministic', 'llm_reviewed', 'llm_structured'];
  const modeLabels = {
    auto: 'Auto planner',
    deterministic: 'Deterministic',
    llm_reviewed: 'LLM reviewed',
    llm_structured: 'LLM structured',
  };
  const selectedMode = localStorage.getItem(PLANNER_MODE_STORAGE) || plannerModeSel.value || 'auto';
  plannerModeSel.innerHTML = '';
  for (const mode of modes) {
    const opt = document.createElement('option');
    opt.value = mode;
    opt.textContent = modeLabels[mode] || mode;
    plannerModeSel.appendChild(opt);
  }
  plannerModeSel.value = modes.includes(selectedMode) ? selectedMode : 'auto';

  const profiles = Array.isArray(caps.standards_profiles)
    ? caps.standards_profiles
    : ['apartment_compact', 'comfortable_home', 'accessible'];
  const profileLabels = {
    apartment_compact: 'Compact apartment',
    compact_hdb: 'Compact HDB',
    comfortable_home: 'Comfortable home',
    accessible: 'Accessible',
    rental_room: 'Rental room',
    hdb_bto: 'HDB/BTO',
    kitchen_basic: 'Kitchen',
    bedroom_basic: 'Bedroom',
    bathroom_basic: 'Bathroom',
  };
  const selectedProfile = localStorage.getItem(PROFILE_STORAGE) || standardsProfileSel.value || 'apartment_compact';
  standardsProfileSel.innerHTML = '';
  for (const profile of profiles) {
    const opt = document.createElement('option');
    opt.value = profile;
    opt.textContent = profileLabels[profile] || profile;
    standardsProfileSel.appendChild(opt);
  }
  standardsProfileSel.value = profiles.includes(selectedProfile) ? selectedProfile : 'apartment_compact';
}

function hydrateModelPlaceholder() {
  const provider = providerSel.value;
  const defaults = serverStatus?.default_models || {};
  const model = defaults[provider] || 'provider default model';
  modelInput.placeholder = `Auto (${model})`;
  const spec = providerSpec(provider);
  const known = Array.isArray(spec?.models) ? spec.models.map((item) => item.id).join(', ') : '';
  modelInput.title = known ? `Optional model override. Known: ${known}` : 'Optional model override';
}

function openChat() {
  panelEl.classList.add('open');
  inputEl.focus();
}

function toggleChat() {
  panelEl.classList.toggle('open');
  if (panelEl.classList.contains('open')) inputEl.focus();
}

function providerHasCredential(provider, keys) {
  if (!provider) return false;
  const spec = providerSpec(provider);
  if (!spec && LOCAL_PROVIDER_IDS.has(provider)) return true;
  if (spec?.requires_api_key === false) return spec.command_available !== false;
  if (keys[provider]) return true;
  const envProviders = Array.isArray(serverStatus?.providers_with_env_keys)
    ? serverStatus.providers_with_env_keys
    : [];
  return envProviders.includes(provider);
}

function newConversationId() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setStatus(text, isError = false) {
  if (!text) {
    statusEl.textContent = '';
    statusEl.style.display = 'none';
    return;
  }

  statusEl.textContent = text;
  statusEl.style.display = '';
  statusEl.style.color = isError ? '#ef4444' : '#a78bfa';
}

function attachmentLimits() {
  const caps = serverStatus?.capabilities || {};
  return {
    maxCount: Number(caps.max_image_attachments) || DEFAULT_MAX_ATTACHMENTS,
    maxBytes: (Number(caps.max_image_attachment_mb) || 5) * 1024 * 1024 || DEFAULT_MAX_ATTACHMENT_BYTES,
    mimeTypes: Array.isArray(caps.image_mime_types) ? caps.image_mime_types : [],
  };
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

async function addImageFiles(files) {
  const selected = Array.from(files || []);
  if (selected.length === 0) return;

  const limits = attachmentLimits();
  const allowed = new Set(limits.mimeTypes);

  for (const file of selected) {
    if (pendingAttachments.length >= limits.maxCount) {
      setStatus(`Attach up to ${limits.maxCount} image references.`, true);
      break;
    }
    if (!file.type.startsWith('image/') || (allowed.size > 0 && !allowed.has(file.type))) {
      setStatus(`${file.name} is not a supported image type.`, true);
      continue;
    }
    if (file.size > limits.maxBytes) {
      setStatus(`${file.name} is larger than ${Math.round(limits.maxBytes / 1024 / 1024)} MB.`, true);
      continue;
    }

    try {
      const dataUrl = await readFileAsDataUrl(file);
      pendingAttachments.push({
        name: file.name,
        mime_type: file.type,
        data_url: dataUrl,
      });
      setStatus('');
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  renderAttachments();
}

function renderAttachments() {
  attachmentsEl.innerHTML = '';
  attachmentsEl.classList.toggle('has-items', pendingAttachments.length > 0);

  pendingAttachments.forEach((attachment, index) => {
    const item = document.createElement('div');
    item.className = 'chat-attachment';

    const img = document.createElement('img');
    img.src = attachment.data_url;
    img.alt = '';

    const label = document.createElement('span');
    label.textContent = attachment.name;

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.title = 'Remove image reference';
    remove.textContent = 'x';
    remove.addEventListener('click', () => {
      pendingAttachments.splice(index, 1);
      renderAttachments();
    });

    item.appendChild(img);
    item.appendChild(label);
    item.appendChild(remove);
    attachmentsEl.appendChild(item);
  });
}

function clearAttachments() {
  pendingAttachments = [];
  renderAttachments();
}

function attachmentTranscript(text, attachments) {
  if (attachments.length === 0) return text;
  const names = attachments.map((item) => item.name).join(', ');
  return `${text}\nAttached ${attachments.length} image reference${attachments.length === 1 ? '' : 's'}: ${names}`;
}

function appendMessage(role, text) {
  const div = document.createElement('div');
  div.className = `chat-msg chat-${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function appendTool(action) {
  maybeShowSightlineOverlay(action);
  if (action.result_json?.requires_confirmation) {
    appendConfirmationCard(action.result_json.confirmation);
    return;
  }

  const args = action.args && Object.keys(action.args).length > 0 ? ` ${JSON.stringify(action.args)}` : '';
  const elapsed = action.elapsed_ms !== undefined ? ` (${action.elapsed_ms}ms)` : '';
  const details = document.createElement('details');
  details.className = 'chat-msg chat-tool chat-tool-details';

  const summary = document.createElement('summary');
  summary.textContent = `${action.tool}${elapsed}`;

  const body = document.createElement('pre');
  body.textContent = `${args ? `Args: ${args}\n` : ''}${action.result}`;

  details.appendChild(summary);
  details.appendChild(body);
  messagesEl.appendChild(details);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendConfirmationCard(confirmation) {
  if (!confirmation || !confirmation.token) return;
  const card = document.createElement('div');
  card.className = 'chat-confirm-card';

  const title = document.createElement('strong');
  title.textContent = 'Confirmation required';

  const summary = document.createElement('p');
  summary.textContent = confirmation.summary || `Run ${confirmation.tool}`;

  const args = document.createElement('pre');
  args.textContent = JSON.stringify(confirmation.args || {}, null, 2);

  const actions = document.createElement('div');
  actions.className = 'chat-plan-actions';

  const confirmBtn = document.createElement('button');
  confirmBtn.type = 'button';
  confirmBtn.textContent = 'Confirm';
  const statusLine = document.createElement('div');
  statusLine.className = 'chat-plan-status';
  confirmBtn.addEventListener('click', () => confirmToolAction(confirmation.token, statusLine, confirmBtn));

  actions.appendChild(confirmBtn);
  card.appendChild(title);
  card.appendChild(summary);
  card.appendChild(args);
  card.appendChild(actions);
  card.appendChild(statusLine);
  messagesEl.appendChild(card);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function confirmToolAction(token, statusLine, confirmBtn) {
  confirmBtn.disabled = true;
  statusLine.textContent = 'Confirming...';
  try {
    const res = await fetch(`/api/tool-confirmations/${encodeURIComponent(token)}/confirm`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || `Confirm failed with HTTP ${res.status}`);
    statusLine.textContent = data.summary || 'Action completed.';
    appendMessage('assistant', data.summary || 'Action completed.');
    persistTranscript('assistant', data.summary || 'Action completed.');
    if (Array.isArray(data.actions)) {
      for (const action of data.actions) appendTool(action);
    }
    await refreshLayoutFromServer();
  } catch (err) {
    statusLine.textContent = err.message || String(err);
    appendMessage('error', statusLine.textContent);
    persistTranscript('error', statusLine.textContent);
    confirmBtn.disabled = false;
  }
}

function appendPlanCard(plan) {
  if (!plan || !plan.id) return;

  const card = document.createElement('div');
  card.className = 'chat-plan-card';

  const header = document.createElement('div');
  header.className = 'chat-plan-header';

  const title = document.createElement('div');
  title.className = 'chat-plan-title';
  title.textContent = plan.title || 'Concept plan';

  const badge = document.createElement('span');
  badge.className = 'chat-plan-badge';
  badge.textContent = plan.planner?.provider_reviewed ? 'LLM reviewed' : (plan.status || 'draft');

  header.appendChild(title);
  header.appendChild(badge);
  card.appendChild(header);

  const brief = document.createElement('p');
  brief.className = 'chat-plan-brief';
  brief.textContent = plan.brief || '';
  card.appendChild(brief);

  const tabs = document.createElement('div');
  tabs.className = 'chat-scenario-tabs';
  const tabLabels = (Array.isArray(plan.zones) && plan.zones.length > 0)
    ? plan.zones.slice(0, 5).map((zone) => zone.name || 'Zone')
    : ['Option A', 'Option B', 'Option C'];
  tabLabels.forEach((label, index) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = `chat-scenario-tab${index === 0 ? ' active' : ''}`;
    tab.textContent = label;
    tab.addEventListener('click', () => {
      tabs.querySelectorAll('.chat-scenario-tab').forEach((item) => item.classList.remove('active'));
      tab.classList.add('active');
    });
    tabs.appendChild(tab);
  });
  card.appendChild(tabs);

  const meta = document.createElement('div');
  meta.className = 'chat-plan-meta';
  const planner = plan.planner || {};
  const profile = plan.standards_profile || {};
  const readiness = (plan.apply_readiness || plan.validation_status || 'needs_review').replaceAll('_', ' ');
  meta.textContent = `${readiness} · ${planner.label || planner.mode || 'Haus planner'} · ${profile.label || 'Compact apartment'} · confidence ${plan.confidence || 'medium'}`;
  card.appendChild(meta);

  if (profile.notes) {
    const note = document.createElement('div');
    note.className = 'chat-plan-warning';
    note.textContent = profile.notes;
    card.appendChild(note);
  }

  const warnings = Array.isArray(plan.warnings) ? plan.warnings : [];
  for (const warning of warnings.slice(0, 3)) {
    const warningEl = document.createElement('div');
    warningEl.className = 'chat-plan-warning';
    warningEl.textContent = warning;
    card.appendChild(warningEl);
  }

  const assumptions = Array.isArray(plan.assumptions) ? plan.assumptions : [];
  if (assumptions.length > 0) {
    const details = document.createElement('details');
    details.className = 'chat-plan-review';
    const summary = document.createElement('summary');
    summary.textContent = 'Assumptions';
    const list = document.createElement('ul');
    assumptions.slice(0, 6).forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      list.appendChild(li);
    });
    details.appendChild(summary);
    details.appendChild(list);
    card.appendChild(details);
  }

  const metrics = plan.metrics || {};
  const metricsGrid = document.createElement('div');
  metricsGrid.className = 'chat-plan-metrics';
  addMetric(metricsGrid, 'Zones', metrics.zone_count ?? (plan.zones || []).length);
  addMetric(metricsGrid, 'Items', metrics.planned_item_count ?? (plan.planned_items || []).length);
  addMetric(metricsGrid, 'Walkway', `${metrics.walkway_target_m || 0.9}m`);
  addMetric(metricsGrid, 'Refs', metrics.reference_count ?? (plan.web_references || []).length);
  card.appendChild(metricsGrid);

  const zones = Array.isArray(plan.zones) ? plan.zones : [];
  if (zones.length > 0) {
    const zoneList = document.createElement('div');
    zoneList.className = 'chat-plan-zones';
    for (const zone of zones.slice(0, 5)) {
      const row = document.createElement('div');
      row.className = 'chat-plan-zone';

      const zoneName = document.createElement('strong');
      zoneName.textContent = zone.name || 'Zone';

      const furniture = Array.isArray(zone.planned_furniture)
        ? zone.planned_furniture.map((item) => item.label || item.furniture_type).filter(Boolean).join(', ')
        : '';

      const details = document.createElement('span');
      details.textContent = `${zone.intent || 'layout'}${zone.estimated_area_m2 ? `, ${zone.estimated_area_m2}m2` : ''}${furniture ? `: ${furniture}` : ''}`;

      row.appendChild(zoneName);
      row.appendChild(details);
      zoneList.appendChild(row);
    }
    card.appendChild(zoneList);
  }

  const refs = Array.isArray(plan.web_references) ? plan.web_references : [];
  if (refs.length > 0) {
    const refList = document.createElement('div');
    refList.className = 'chat-plan-refs';
    for (const ref of refs.slice(0, 3)) {
      const link = document.createElement('a');
      link.href = ref.url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = ref.title || ref.url;
      refList.appendChild(link);
    }
    card.appendChild(refList);
  }

  if (plan.llm_review?.text) {
    const review = document.createElement('details');
    review.className = 'chat-plan-review';
    const summary = document.createElement('summary');
    summary.textContent = 'LLM review';
    const text = document.createElement('p');
    text.textContent = plan.llm_review.text;
    review.appendChild(summary);
    review.appendChild(text);
    card.appendChild(review);
  }

  const statusLine = document.createElement('div');
  statusLine.className = 'chat-plan-status';

  const actions = document.createElement('div');
  actions.className = 'chat-plan-actions';

  const applyBtn = document.createElement('button');
  applyBtn.type = 'button';
  applyBtn.textContent = 'Apply';
  applyBtn.addEventListener('click', () => applyDesignPlan(plan.id, statusLine, applyBtn));

  const reviseBtn = document.createElement('button');
  reviseBtn.type = 'button';
  reviseBtn.textContent = 'Revise';
  reviseBtn.addEventListener('click', () => {
    inputEl.value = `Revise plan ${plan.id}: `;
    inputEl.focus();
    inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
  });

  const downloadBtn = document.createElement('button');
  downloadBtn.type = 'button';
  downloadBtn.textContent = 'Export';
  downloadBtn.addEventListener('click', () => downloadPlanReport(plan.id, statusLine));

  const compareBtn = document.createElement('button');
  compareBtn.type = 'button';
  compareBtn.textContent = 'Compare';
  compareBtn.addEventListener('click', () => {
    fn.compareActiveScenarios?.();
    statusLine.textContent = 'Comparison opened in validation panel.';
    appendMessage('assistant', `Plan link: compare current scenarios for ${plan.id}.`);
    persistTranscript('assistant', `Plan link: compare current scenarios for ${plan.id}.`);
  });

  const validateBtn = document.createElement('button');
  validateBtn.type = 'button';
  validateBtn.textContent = 'Validate';
  validateBtn.addEventListener('click', () => {
    const report = fn.regenerateValidation?.();
    statusLine.textContent = report ? `Validation complete with ${report.warnings?.length || 0} warning(s).` : 'Validation requested.';
    appendMessage('assistant', `Validation link: ${statusLine.textContent}`);
    persistTranscript('assistant', `Validation link: ${statusLine.textContent}`);
  });

  const geometryBtn = document.createElement('button');
  geometryBtn.type = 'button';
  geometryBtn.textContent = 'Show geometry';
  geometryBtn.addEventListener('click', () => {
    const report = fn.regenerateValidation?.();
    if (report?.overlays) fn.showValidationOverlay?.(report.overlays);
    statusLine.textContent = 'Geometry overlay shown.';
    appendMessage('assistant', `Geometry link: overlay shown for ${plan.id}.`);
    persistTranscript('assistant', `Geometry link: overlay shown for ${plan.id}.`);
  });

  actions.appendChild(applyBtn);
  actions.appendChild(reviseBtn);
  actions.appendChild(compareBtn);
  actions.appendChild(validateBtn);
  actions.appendChild(downloadBtn);
  actions.appendChild(geometryBtn);
  card.appendChild(actions);
  card.appendChild(statusLine);

  messagesEl.appendChild(card);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMetric(parent, labelText, valueText) {
  const metric = document.createElement('div');
  metric.className = 'chat-plan-metric';

  const value = document.createElement('strong');
  value.textContent = String(valueText ?? '-');

  const label = document.createElement('span');
  label.textContent = labelText;

  metric.appendChild(value);
  metric.appendChild(label);
  parent.appendChild(metric);
}

async function refreshLayoutFromServer() {
  if (!fn.applyLayoutData) return;
  const res = await fetch(`./mcp-layout.json?t=${Date.now()}`);
  if (!res.ok) return;
  const data = await res.json();
  if (Array.isArray(data.items)) {
    fn.applyLayoutData(data, { frame: false });
  }
}

async function applyDesignPlan(planId, statusLine, applyBtn) {
  applyBtn.disabled = true;
  statusLine.textContent = 'Applying plan...';

  try {
    const res = await fetch(`/api/design-plans/${encodeURIComponent(planId)}/apply`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || `Apply failed with HTTP ${res.status}`);

    statusLine.textContent = data.summary || 'Plan applied.';
    appendMessage('assistant', data.summary || 'Plan applied.');
    persistTranscript('assistant', data.summary || 'Plan applied.');

    if (Array.isArray(data.actions)) {
      for (const action of data.actions) {
        appendTool(action);
        persistTranscript('tool', `${action.tool} -> ${action.result}`);
      }
    }

    await refreshLayoutFromServer();
  } catch (err) {
    statusLine.textContent = err.message || String(err);
    appendMessage('error', statusLine.textContent);
    persistTranscript('error', statusLine.textContent);
    applyBtn.disabled = false;
  }
}

async function downloadPlanReport(planId, statusLine) {
  statusLine.textContent = 'Preparing brief...';
  try {
    const res = await fetch(`/api/design-plans/${encodeURIComponent(planId)}/report`);
    if (!res.ok) throw new Error(`Report failed with HTTP ${res.status}`);
    const text = await res.text();
    const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `haus-concept-${planId}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    statusLine.textContent = 'Brief downloaded.';
    appendMessage('assistant', `Report link: downloaded haus-concept-${planId}.md.`);
    persistTranscript('assistant', `Report link: downloaded haus-concept-${planId}.md.`);
  } catch (err) {
    statusLine.textContent = err.message || String(err);
    appendMessage('error', statusLine.textContent);
    persistTranscript('error', statusLine.textContent);
  }
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
  const scopedKey = transcriptStorageKey();
  const transcript = loadJson(scopedKey, loadJson(TRANSCRIPT_STORAGE, []));
  transcript.push({ role, text: sanitizeTranscriptText(text) });
  const trimmed = transcript.slice(-250);
  saveJson(scopedKey, trimmed);
  saveJson(TRANSCRIPT_STORAGE, trimmed);
}

function sanitizeTranscriptText(text) {
  return String(text || '')
    .replace(/data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+/gi, '[redacted image data]')
    .replace(/\b(sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|ant-[A-Za-z0-9_-]{12,})\b/g, '[redacted key]');
}

function renderTranscript() {
  messagesEl.innerHTML = '';
  const transcript = loadJson(transcriptStorageKey(), loadJson(TRANSCRIPT_STORAGE, []));
  for (const msg of transcript) {
    appendMessage(msg.role || 'assistant', msg.text || '');
  }
  if (transcript.length === 0) {
    appendMessage('assistant', 'Upload a floor plan, start from manual room dimensions, or ask for a journey-specific draft plan.');
  }
}

function clearConversation() {
  history = [];
  conversationId = newConversationId();
  localStorage.setItem(CONVERSATION_STORAGE, conversationId);
  saveHistory(history);
  saveJson(transcriptStorageKey(), []);
  saveJson(TRANSCRIPT_STORAGE, []);
  clearAttachments();
  messagesEl.innerHTML = '';
  appendMessage('assistant', 'Conversation cleared.');
  persistTranscript('assistant', 'Conversation cleared.');
}

function recoveryText(errorText) {
  const text = String(errorText || '').toLowerCase();
  if (text.includes('scale') || text.includes('calibration')) return 'Recovery: confirm scale by drawing a known-length segment or build a manual room with width and depth.';
  if (text.includes('door')) return 'Recovery: add door/opening widths in Manual Plan Tools before validating fit or accessibility.';
  if (text.includes('room') || text.includes('boundary')) return 'Recovery: upload a floor plan, trace room boundaries, or use the manual room builder.';
  if (text.includes('product') || text.includes('dimension')) return 'Recovery: enter product width, depth, height, and source confidence before checking fit.';
  if (text.includes('web_search') || text.includes('web search') || text.includes('reference')) return 'Recovery: web search is unavailable or disabled. Continue with deterministic planning, or re-enable web search in chat settings.';
  if (text.includes('confirmation') || text.includes('token')) return 'Recovery: the confirmation expired. Ask Haus to repeat the edit and confirm the new card.';
  if (text.includes('unsupported') || text.includes('image type')) return 'Recovery: upload a PNG, JPEG, WEBP, GIF, or a supported Haus JSON layout.';
  if (text.includes('vector')) return 'Recovery: use manual room dimensions or trace rooms if floor-plan vectorization fails.';
  return '';
}

function appendRecoveryMessage(errorText) {
  const recovery = recoveryText(errorText);
  if (!recovery) return;
  appendMessage('assistant', recovery);
  persistTranscript('assistant', recovery);
}

function parseSseBlock(block) {
  const lines = block.split('\n');
  let event = 'message';
  let data = '';
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data: { delta: data } };
  }
}

async function sendStream(payload, loading) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed with HTTP ${res.status}`);

  loading.remove();
  const assistantEl = appendMessage('assistant', '');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let responseText = '';
  let doneData = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed) continue;
      if (parsed.event === 'text') {
        responseText += parsed.data.delta || '';
        assistantEl.textContent = responseText;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (parsed.event === 'error') {
        assistantEl.remove();
        throw new Error(parsed.data.error || 'Stream failed');
      } else if (parsed.event === 'done') {
        doneData = parsed.data;
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer.trim());
    if (parsed?.event === 'done') doneData = parsed.data;
  }
  if (!responseText && doneData?.response) {
    responseText = doneData.response;
    assistantEl.textContent = responseText;
  }
  persistTranscript('assistant', responseText);
  return doneData || { response: responseText };
}

function webllmContentText(content) {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  const lines = [];
  for (const block of content) {
    if (!block || typeof block !== 'object') continue;
    if (block.type === 'text') lines.push(block.text || '');
    else if (block.type === 'tool_result') lines.push(`Tool result: ${block.content || ''}`);
    else if (block.type === 'image') lines.push('[image attachment omitted by text-only WebLLM]');
  }
  return lines.filter(Boolean).join('\n');
}

function webllmMessages(payload) {
  const projectContext = payload.project_context ? JSON.stringify(payload.project_context).slice(0, 8000) : '{}';
  const system = [
    'You are running as a text-only browser local runtime for Haus chat.',
    'Do not claim to edit the Haus scene. If the user asks for an applied edit, describe the safe Haus action or deterministic planner step instead.',
    '',
    'Haus project context:',
    projectContext,
  ].join('\n');
  const out = [{ role: 'system', content: system }];
  for (const msg of (Array.isArray(payload.history) ? payload.history.slice(-16) : [])) {
    const role = msg.role === 'assistant' ? 'assistant' : 'user';
    const text = webllmContentText(msg.content);
    if (text) out.push({ role, content: text });
  }
  let userText = payload.message || '';
  if (Array.isArray(payload.attachments) && payload.attachments.length > 0) {
    const names = payload.attachments.map((item) => item.name).filter(Boolean).join(', ');
    userText += `\nAttached image references omitted by text-only WebLLM: ${names}`;
  }
  out.push({ role: 'user', content: userText });
  return out;
}

async function getWebllmEngine(model, loading) {
  if (!navigator.gpu) throw new Error('WebLLM requires a WebGPU-capable browser.');
  if (webllmEngine && webllmModel === model) return webllmEngine;
  loading.textContent = `Loading WebLLM ${model}...`;
  const webllm = await import('@mlc-ai/web-llm');
  webllmEngine = await webllm.CreateMLCEngine(model, {
    initProgressCallback: (progress) => {
      const text = progress?.text || progress?.progress ? `${progress.text || 'Loading WebLLM'} ${Math.round((progress.progress || 0) * 100)}%` : `Loading WebLLM ${model}...`;
      loading.textContent = text;
    },
  });
  webllmModel = model;
  return webllmEngine;
}

async function sendWebllm(payload, loading) {
  const model = payload.model || serverStatus?.default_models?.webllm || 'Llama-3.1-8B-Instruct-q4f32_1-MLC';
  const engine = await getWebllmEngine(model, loading);
  const messages = webllmMessages({ ...payload, model });
  loading.remove();
  const assistantEl = appendMessage('assistant', '');
  let responseText = '';
  const chunks = await engine.chat.completions.create({
    messages,
    temperature: 0.2,
    stream: true,
    stream_options: { include_usage: true },
  });
  for await (const chunk of chunks) {
    const delta = chunk.choices?.[0]?.delta?.content || '';
    if (!delta) continue;
    responseText += delta;
    assistantEl.textContent = responseText;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  const updatedHistory = [
    ...(Array.isArray(payload.history) ? payload.history : []),
    { role: 'user', content: [{ type: 'text', text: payload.message || '' }] },
    { role: 'assistant', content: [{ type: 'text', text: responseText }] },
  ];
  persistTranscript('assistant', responseText);
  return {
    response: responseText,
    history: updatedHistory,
    provider: 'webllm',
    model,
    custom_model: Boolean(payload.model),
    actions: [],
    request_id: 'webllm-browser',
  };
}

async function sendJson(payload, loading) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = { error: `Invalid JSON response (HTTP ${res.status})` };
  }
  loading.remove();
  if (!res.ok || data.error) throw new Error(data.error || `Request failed with HTTP ${res.status}`);
  appendMessage('assistant', data.response || '');
  persistTranscript('assistant', data.response || '');
  return data;
}

async function send() {
  if (sending) return;

  const typedText = inputEl.value.trim();
  const attachmentsForSend = pendingAttachments.map((item) => ({ ...item }));
  const text = typedText || (attachmentsForSend.length > 0 ? 'Replicate this visual reference in the current layout.' : '');
  if (!text) return;

  const keys = getKeys();
  const selectedProvider = providerSel.value || '';
  const provider = providerHasCredential(selectedProvider, keys) ? selectedProvider : '';
  const apiKey = provider ? keys[provider] || '' : '';

  const model = modelInput.value.trim();
  const plannerMode = plannerModeSel.value || 'auto';
  const standardsProfile = standardsProfileSel.value || 'apartment_compact';
  const webSearchDisabled = Boolean(disableWebSearchEl?.checked);
  const transcriptText = attachmentTranscript(text, attachmentsForSend);
  const projectContext = fn.getProjectChatContext ? fn.getProjectChatContext(text) : null;

  inputEl.value = '';
  clearAttachments();
  appendMessage('user', transcriptText);
  persistTranscript('user', transcriptText);

  inputEl.disabled = true;
  sendBtn.disabled = true;
  sending = true;

  const loading = document.createElement('div');
  loading.className = 'chat-msg chat-loading';
  loading.textContent = attachmentsForSend.length > 0 ? 'Planning with references...' : 'Planning with tools...';
  messagesEl.appendChild(loading);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const payload = {
      message: text,
      history,
      provider,
      model,
      api_key: apiKey,
      conversation_id: conversationId,
      planner_mode: plannerMode,
      standards_profile: standardsProfile,
      web_search_disabled: webSearchDisabled,
      privacy: fn.getPrivacySettings ? fn.getPrivacySettings() : { disable_web_search: webSearchDisabled },
      project_context: projectContext,
      command_route: projectContext?.route || '',
      attachments: attachmentsForSend,
    };
    const providerCaps = providerSpec(provider)?.capabilities || [];
    const canStream = Boolean(serverStatus?.capabilities?.provider_native_streaming)
      && Boolean(window.ReadableStream)
      && providerCaps.includes('streaming');
    const data = BROWSER_PROVIDER_IDS.has(provider)
      ? await sendWebllm(payload, loading)
      : canStream ? await sendStream(payload, loading) : await sendJson(payload, loading);

    if (Array.isArray(data.actions) && data.actions.length > 0) {
      for (const action of data.actions) {
        appendTool(action);
        persistTranscript('tool', `${action.tool} -> ${action.result}`);
      }
    }

    if (data.pending_plan) {
      appendPlanCard(data.pending_plan);
    }

    history = Array.isArray(data.history) ? data.history : [];
    saveHistory(history);

    if (data.request_id) setStatus(`Last request: ${data.request_id}`, false);
  } catch (err) {
    if (loading.isConnected) loading.remove();
    const textErr = `Request failed: ${err.message}`;
    appendMessage('error', textErr);
    persistTranscript('error', textErr);
    appendRecoveryMessage(textErr);
  } finally {
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
    sending = false;
  }
}
