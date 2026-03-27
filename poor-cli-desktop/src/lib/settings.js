// settings page — fetches config options, renders categorized form
import { rpc } from './rpc.js';

const categories = { // display name -> config key prefix
  'General': 'ui',
  'Fonts': 'fonts',
  'API Keys': 'api_keys',
  'Providers': 'model',
  'Security': 'security',
  'Sandbox': 'sandbox',
  'Plan Mode': 'plan_mode',
  'Checkpoints': 'checkpoint',
  'History': 'history',
  'Context': 'context_compression',
  'Cost': 'cost_guardrail',
  'Fallback': 'fallback',
};

const apiKeyDefs = [
  { id: 'gemini', label: 'Gemini (Google)', env: 'GEMINI_API_KEY', hint: 'makersuite.google.com/app/apikey' },
  { id: 'openai', label: 'OpenAI', env: 'OPENAI_API_KEY', hint: 'platform.openai.com/api-keys' },
  { id: 'anthropic', label: 'Anthropic (Claude)', env: 'ANTHROPIC_API_KEY', hint: 'console.anthropic.com' },
  { id: 'ollama', label: 'Ollama (local)', env: 'OLLAMA_API_KEY', hint: 'No key needed for local models' },
  { id: 'brave', label: 'Brave Search', env: 'BRAVE_SEARCH_API_KEY', hint: 'brave.com/search/api' },
];

const defaultOptions = [ // fallback when backend unavailable
  { path: 'ui.theme', value: 'github-light', choices: ['github-light', 'quiet-light', 'solarized-light', 'one-dark', 'dracula', 'github-dark', 'monokai', 'nord'] },
  { path: 'ui.crt_effect', value: false, isBoolean: true },
  { path: 'ui.stream', value: true, isBoolean: true },
  { path: 'ui.markdown', value: true, isBoolean: true },
  { path: 'model.default_provider', value: 'openai', choices: ['gemini', 'openai', 'anthropic', 'ollama'] },
  { path: 'model.temperature', value: 0.7 },
  { path: 'model.max_tokens', value: 4096 },
  { path: 'security.require_approval', value: true, isBoolean: true },
  { path: 'security.audit_log', value: true, isBoolean: true },
  { path: 'sandbox.enabled', value: false, isBoolean: true },
  { path: 'sandbox.preset', value: 'permissive', choices: ['strict', 'moderate', 'permissive'] },
  { path: 'plan_mode.auto_plan', value: false, isBoolean: true },
  { path: 'checkpoint.enabled', value: true, isBoolean: true },
  { path: 'checkpoint.interval_minutes', value: 5 },
  { path: 'history.max_entries', value: 1000 },
  { path: 'history.persist', value: true, isBoolean: true },
  { path: 'context_compression.enabled', value: true, isBoolean: true },
  { path: 'cost_guardrail.enabled', value: false, isBoolean: true },
  { path: 'cost_guardrail.max_cost', value: 10.0 },
  { path: 'fallback.enabled', value: true, isBoolean: true },
  { path: 'fallback.chain', value: 'gemini,openai,ollama' },
];

export async function initSettings() {
  const sidebar = document.querySelector('.settings-sidebar');
  const content = document.getElementById('settings-content');
  // build category nav
  for (const [name] of Object.entries(categories)) {
    const el = document.createElement('div');
    el.className = 'settings-cat';
    el.textContent = name;
    el.addEventListener('click', () => {
      document.querySelectorAll('.settings-cat').forEach(c => c.classList.remove('active'));
      el.classList.add('active');
      const target = content.querySelector(`[data-category="${name}"]`);
      if (target) target.scrollIntoView({ behavior: 'smooth' });
    });
    sidebar.appendChild(el);
  }
  renderOptions(content, defaultOptions); // render defaults immediately
  rpc('list_config_options', {}).then(result => { // update from backend if available
    const options = result.options || result || [];
    if (options.length) renderOptions(content, options);
  }).catch(() => {});
  rpc('get_api_key_status', {}).then(status => { // update key status from backend
    if (status && typeof status === 'object') {
      for (const [provider, info] of Object.entries(status)) {
        const dot = document.querySelector(`.api-key-status[data-provider="${provider}"]`);
        if (dot) {
          dot.classList.toggle('set', !!info.isSet);
          dot.title = info.isSet ? 'Key is set' : 'No key configured';
        }
      }
    }
  }).catch(() => {});
}

function renderApiKeysGroup() {
  const group = document.createElement('div');
  group.className = 'settings-group';
  group.dataset.category = 'API Keys';
  group.innerHTML = '<h2>API Keys</h2>';
  const stored = JSON.parse(localStorage.getItem('poor-cli-api-keys') || '{}');
  for (const def of apiKeyDefs) {
    const row = document.createElement('div');
    row.className = 'settings-row api-key-row';
    const hasKey = !!stored[def.id];
    row.innerHTML = `
      <div class="settings-row-info">
        <label><span class="api-key-status${hasKey ? ' set' : ''}" data-provider="${def.id}" title="${hasKey ? 'Key is set' : 'No key configured'}"></span>${def.label}</label>
        <div class="desc">${def.env} &mdash; <a class="api-key-hint" href="#">${def.hint}</a></div>
      </div>
      <div class="api-key-actions">
        <input type="password" class="api-key-input" placeholder="${hasKey ? '••••••••' : 'Paste API key...'}" data-id="${def.id}" data-env="${def.env}" />
        <button class="btn btn-sm api-key-toggle" title="Show/hide">Show</button>
        <button class="btn btn-sm btn-primary api-key-save" title="Save">Save</button>
        ${hasKey ? '<button class="btn btn-sm api-key-remove" title="Remove">Remove</button>' : ''}
      </div>`;
    const input = row.querySelector('.api-key-input');
    row.querySelector('.api-key-toggle').addEventListener('click', () => {
      input.type = input.type === 'password' ? 'text' : 'password';
    });
    row.querySelector('.api-key-save').addEventListener('click', () => {
      const val = input.value.trim();
      if (!val) return;
      stored[def.id] = val;
      localStorage.setItem('poor-cli-api-keys', JSON.stringify(stored));
      rpc('set_api_key', { provider: def.id, apiKey: val, persist: true, reloadActiveProvider: true }).catch(() => {});
      input.value = '';
      input.placeholder = '••••••••';
      const dot = row.querySelector('.api-key-status');
      dot.classList.add('set');
      dot.title = 'Key is set';
      if (!row.querySelector('.api-key-remove')) { // add remove btn
        const rm = document.createElement('button');
        rm.className = 'btn btn-sm api-key-remove';
        rm.title = 'Remove';
        rm.textContent = 'Remove';
        rm.addEventListener('click', () => removeKey(def, row, stored));
        row.querySelector('.api-key-actions').appendChild(rm);
      }
    });
    const rmBtn = row.querySelector('.api-key-remove');
    if (rmBtn) rmBtn.addEventListener('click', () => removeKey(def, row, stored));
    group.appendChild(row);
  }
  return group;
}

function removeKey(def, row, stored) {
  delete stored[def.id];
  localStorage.setItem('poor-cli-api-keys', JSON.stringify(stored));
  // no backend RPC for key removal yet — only clear local cache
  const dot = row.querySelector('.api-key-status');
  dot.classList.remove('set');
  dot.title = 'No key configured';
  row.querySelector('.api-key-input').placeholder = 'Paste API key...';
  const rm = row.querySelector('.api-key-remove');
  if (rm) rm.remove();
}

function renderOptions(container, options) {
  container.innerHTML = '';
  const grouped = {};
  for (const opt of options) {
    const prefix = (opt.path || '').split('.')[0] || 'other';
    const catName = Object.entries(categories).find(([, v]) => v === prefix)?.[0] || capitalize(prefix);
    if (!grouped[catName]) grouped[catName] = [];
    grouped[catName].push(opt);
  }
  // render in category order
  const orderedCats = Object.keys(categories);
  for (const cat of orderedCats) {
    if (cat === 'API Keys') { container.appendChild(renderApiKeysGroup()); continue; }
    const opts = grouped[cat];
    if (!opts) continue;
    const group = document.createElement('div');
    group.className = 'settings-group';
    group.dataset.category = cat;
    group.innerHTML = `<h2>${cat}</h2>`;
    for (const opt of opts) {
      const row = document.createElement('div');
      row.className = 'settings-row';
      const info = document.createElement('div');
      info.className = 'settings-row-info';
      const label = opt.path.split('.').pop().replace(/_/g, ' ');
      info.innerHTML = `<label>${capitalize(label)}</label><div class="desc">${opt.path}</div>`;
      row.appendChild(info);
      if (opt.isBoolean || typeof opt.value === 'boolean') {
        const toggle = document.createElement('label');
        toggle.className = 'toggle';
        toggle.innerHTML = `<input type="checkbox" ${opt.value ? 'checked' : ''}><span class="toggle-slider"></span>`;
        toggle.querySelector('input').addEventListener('change', (e) => {
          rpc('set_config', { keyPath: opt.path, value: e.target.checked }).catch(() => {});
          if (opt.path === 'ui.crt_effect') document.documentElement.classList.toggle('crt', e.target.checked);
        });
        row.appendChild(toggle);
      } else if (opt.choices && opt.choices.length) {
        const sel = document.createElement('select');
        opt.choices.forEach(c => {
          const o = document.createElement('option');
          o.value = c; o.textContent = c;
          if (c === String(opt.value)) o.selected = true;
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => {
          rpc('set_config', { keyPath: opt.path, value: sel.value }).catch(() => {});
          if (opt.path === 'ui.theme') document.documentElement.setAttribute('data-theme', sel.value);
        });
        row.appendChild(sel);
      } else {
        const input = document.createElement('input');
        input.type = 'text';
        input.value = opt.value ?? '';
        input.addEventListener('change', () => {
          const v = isNaN(input.value) ? input.value : Number(input.value);
          rpc('set_config', { keyPath: opt.path, value: v }).catch(() => {});
        });
        row.appendChild(input);
      }
      group.appendChild(row);
    }
    container.appendChild(group);
  }
}

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
