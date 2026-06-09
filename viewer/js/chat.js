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

let history = [];
let serverStatus = null;
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
const DEFAULT_MAX_ATTACHMENTS = 3;
const DEFAULT_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;

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
  });
  plannerModeSel.addEventListener('change', () => {
    localStorage.setItem(PLANNER_MODE_STORAGE, plannerModeSel.value);
  });
  standardsProfileSel.addEventListener('change', () => {
    localStorage.setItem(PROFILE_STORAGE, standardsProfileSel.value);
  });

  clearBtn.addEventListener('click', clearConversation);

  settingsBtn.addEventListener('click', () => {
    const open = settingsEl.style.display !== 'none';
    settingsEl.style.display = open ? 'none' : '';
    if (!open) loadKeyField();
  });

  keySaveBtn.addEventListener('click', saveKey);
  keyForgetBtn.addEventListener('click', forgetKey);

  history = loadJson(HISTORY_STORAGE, []);
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

function getKeys() {
  return { ...loadJson(KEYS_STORAGE, {}), ...sessionKeys };
}

function setStoredKeys(keys) {
  saveJson(KEYS_STORAGE, keys);
}

function loadKeyField() {
  const keys = getKeys();
  const storedKeys = loadJson(KEYS_STORAGE, {});
  const provider = providerSel.value;
  keyInput.value = keys[provider] || '';
  keyPersistEl.checked = Boolean(storedKeys[provider]);
  if (storedKeys[provider]) keyStatusEl.textContent = 'Key loaded from browser storage';
  else if (sessionKeys[provider]) keyStatusEl.textContent = 'Key available for this tab only';
  else keyStatusEl.textContent = '';
}

function saveKey() {
  const storedKeys = loadJson(KEYS_STORAGE, {});
  const provider = providerSel.value;
  const value = keyInput.value.trim();

  delete storedKeys[provider];
  delete sessionKeys[provider];

  if (value && keyPersistEl.checked) {
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
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/chat/status');
    if (!res.ok) throw new Error(`status ${res.status}`);
    serverStatus = await res.json();
    refreshProviders();
    refreshPlannerControls();
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
    providerSel.value = providersFromServer[0];
    localStorage.setItem(PROVIDER_STORAGE, providerSel.value);
  }

  hydrateModelPlaceholder();
  loadKeyField();
  refreshProviderStatus(keys, envProviders);
}

function providerLabel(provider) {
  return { anthropic: 'Anthropic', openai: 'OpenAI', gemini: 'Gemini' }[provider] || provider;
}

function refreshProviderStatus(keys = getKeys(), envProviders = new Set(Array.isArray(serverStatus?.providers_with_env_keys) ? serverStatus.providers_with_env_keys : [])) {
  const provider = providerSel.value;
  if (!provider || keys[provider] || envProviders.has(provider)) setStatus('');
  else setStatus('Deterministic planner available. Add a provider key for LLM-reviewed plans.', false);
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
    : ['compact_hdb', 'comfortable_home', 'accessible'];
  const profileLabels = {
    compact_hdb: 'Compact HDB',
    comfortable_home: 'Comfortable home',
    accessible: 'Accessible',
    kitchen_basic: 'Kitchen',
    bedroom_basic: 'Bedroom',
    bathroom_basic: 'Bathroom',
  };
  const selectedProfile = localStorage.getItem(PROFILE_STORAGE) || standardsProfileSel.value || 'compact_hdb';
  standardsProfileSel.innerHTML = '';
  for (const profile of profiles) {
    const opt = document.createElement('option');
    opt.value = profile;
    opt.textContent = profileLabels[profile] || profile;
    standardsProfileSel.appendChild(opt);
  }
  standardsProfileSel.value = profiles.includes(selectedProfile) ? selectedProfile : 'compact_hdb';
}

function hydrateModelPlaceholder() {
  const provider = providerSel.value;
  const defaults = serverStatus?.default_models || {};
  const model = defaults[provider] || 'provider default model';
  modelInput.placeholder = `Auto (${model})`;
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
  if (keys[provider]) return true;
  const envProviders = Array.isArray(serverStatus?.providers_with_env_keys)
    ? serverStatus.providers_with_env_keys
    : [];
  return envProviders.includes(provider);
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
  badge.textContent = plan.status || 'draft';

  header.appendChild(title);
  header.appendChild(badge);
  card.appendChild(header);

  const brief = document.createElement('p');
  brief.className = 'chat-plan-brief';
  brief.textContent = plan.brief || '';
  card.appendChild(brief);

  const meta = document.createElement('div');
  meta.className = 'chat-plan-meta';
  const planner = plan.planner || {};
  const profile = plan.standards_profile || {};
  const readiness = (plan.apply_readiness || plan.validation_status || 'needs_review').replaceAll('_', ' ');
  meta.textContent = `${readiness} · ${planner.label || planner.mode || 'Haus planner'} · ${profile.label || 'Compact HDB'} · confidence ${plan.confidence || 'medium'}`;
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
  downloadBtn.textContent = 'Download brief';
  downloadBtn.addEventListener('click', () => downloadPlanReport(plan.id, statusLine));

  actions.appendChild(applyBtn);
  actions.appendChild(reviseBtn);
  actions.appendChild(downloadBtn);
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
  const transcript = loadJson(TRANSCRIPT_STORAGE, []);
  transcript.push({ role, text: sanitizeTranscriptText(text) });
  saveJson(TRANSCRIPT_STORAGE, transcript.slice(-250));
}

function sanitizeTranscriptText(text) {
  return String(text || '')
    .replace(/data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+/gi, '[redacted image data]')
    .replace(/\b(sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|ant-[A-Za-z0-9_-]{12,})\b/g, '[redacted key]');
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
  clearAttachments();
  messagesEl.innerHTML = '';
  appendMessage('assistant', 'Conversation cleared.');
  persistTranscript('assistant', 'Conversation cleared.');
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
  const standardsProfile = standardsProfileSel.value || 'compact_hdb';
  const transcriptText = attachmentTranscript(text, attachmentsForSend);

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
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history,
        provider,
        model,
        api_key: apiKey,
        planner_mode: plannerMode,
        standards_profile: standardsProfile,
        attachments: attachmentsForSend,
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

    if (data.pending_plan) {
      appendPlanCard(data.pending_plan);
    }

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
