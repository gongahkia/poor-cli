// settings page — fetches config options, renders categorized form
import { rpc } from './rpc.js';

const categories = { // display name -> config key prefix
  'General': 'ui',
  'Fonts': 'fonts',
  'API Keys': 'api_keys',
  'Model': 'model',
  'Security': 'security',
  'Sandbox': 'sandbox',
  'Plan Mode': 'plan_mode',
  'Checkpoints': 'checkpoint',
  'Agentic': 'agentic',
  'History': 'history',
  'Context Compression': 'context_compression',
  'Output Truncation': 'output_truncation',
  'Cost Guardrails': 'cost_guardrails',
  'Fallback': 'fallback',
  'Economy': 'economy',
  'Repo Index': 'repo_index',
  'Tasks': 'tasks',
};

const apiKeyDefs = [
  { id: 'gemini', label: 'Gemini (Google)', env: 'GEMINI_API_KEY', hint: 'makersuite.google.com/app/apikey' },
  { id: 'openai', label: 'OpenAI', env: 'OPENAI_API_KEY', hint: 'platform.openai.com/api-keys' },
  { id: 'anthropic', label: 'Anthropic (Claude)', env: 'ANTHROPIC_API_KEY', hint: 'console.anthropic.com' },
  { id: 'ollama', label: 'Ollama (local)', env: 'OLLAMA_API_KEY', hint: 'No key needed for local models' },
  { id: 'brave', label: 'Brave Search', env: 'BRAVE_SEARCH_API_KEY', hint: 'brave.com/search/api' },
];

// fallback options using exact backend field names
const defaultOptions = [
  // ui
  { path: 'ui.theme', value: 'github-light', choices: [...LIGHT_THEMES, ...DARK_THEMES] },
  { path: 'ui.tab_layout', value: 'horizontal', choices: ['horizontal', 'vertical'] },
  { path: 'ui.enable_streaming', value: true, isBoolean: true },
  { path: 'ui.markdown_rendering', value: true, isBoolean: true },
  { path: 'ui.show_token_count', value: true, isBoolean: true },
  { path: 'ui.show_tool_calls', value: true, isBoolean: true },
  { path: 'ui.verbose_logging', value: false, isBoolean: true },
  // model
  { path: 'model.provider', value: 'openai', choices: ['gemini', 'openai', 'anthropic', 'ollama'] },
  { path: 'model.routing_mode', value: 'manual', choices: ['manual', 'quality', 'speed', 'cheap', 'private'] },
  { path: 'model.temperature', value: 0.7 },
  { path: 'model.max_tokens', value: null },
  { path: 'model.top_p', value: 0.95 },
  { path: 'model.prompt_caching', value: true, isBoolean: true },
  // security
  { path: 'security.permission_mode', value: 'prompt', choices: ['prompt', 'auto-safe', 'danger-full-access'] },
  { path: 'security.require_permission_for_write', value: true, isBoolean: true },
  { path: 'security.require_permission_for_bash', value: true, isBoolean: true },
  { path: 'security.enable_bash_execution', value: true, isBoolean: true },
  { path: 'security.max_bash_timeout_seconds', value: 60 },
  { path: 'security.unicode_scanning', value: true, isBoolean: true },
  // sandbox
  { path: 'sandbox.default_preset', value: 'workspace-write', choices: ['read-only', 'review-only', 'workspace-write', 'full-access'] },
  // plan mode
  { path: 'plan_mode.enabled', value: true, isBoolean: true },
  { path: 'plan_mode.auto_plan_threshold', value: 2 },
  { path: 'plan_mode.require_approval_for_high_risk', value: true, isBoolean: true },
  { path: 'plan_mode.show_diff_in_plan', value: true, isBoolean: true },
  // checkpoint
  { path: 'checkpoint.enabled', value: true, isBoolean: true },
  { path: 'checkpoint.auto_checkpoint_before_write', value: true, isBoolean: true },
  { path: 'checkpoint.max_checkpoints', value: 50 },
  { path: 'checkpoint.max_age_hours', value: 0 },
  { path: 'checkpoint.max_disk_mb', value: 0 },
  // agentic
  { path: 'agentic.max_iterations', value: 25 },
  { path: 'agentic.sub_agent_max_depth', value: 2 },
  { path: 'agentic.sub_agent_timeout', value: 120 },
  // history
  { path: 'history.max_turns', value: 50 },
  { path: 'history.auto_save', value: true, isBoolean: true },
  { path: 'history.restore_on_startup', value: true, isBoolean: true },
  { path: 'history.max_messages_to_restore', value: 20 },
  // context compression
  { path: 'context_compression.enabled', value: true, isBoolean: true },
  { path: 'context_compression.compress_after_turns', value: 20 },
  { path: 'context_compression.preserve_recent_turns', value: 8 },
  // output truncation
  { path: 'output_truncation.enabled', value: true, isBoolean: true },
  { path: 'output_truncation.max_output_chars', value: 32000 },
  { path: 'output_truncation.max_output_lines', value: 500 },
  // cost guardrails
  { path: 'cost_guardrails.session_max_cost_usd', value: 0.0 },
  { path: 'cost_guardrails.task_max_cost_usd', value: 0.0 },
  { path: 'cost_guardrails.pause_on_limit', value: true, isBoolean: true },
  // fallback
  { path: 'fallback.enabled', value: false, isBoolean: true },
  { path: 'fallback.retry_on_rate_limit', value: true, isBoolean: true },
  { path: 'fallback.max_fallback_attempts', value: 3 },
  // economy
  { path: 'economy.preset', value: 'balanced', choices: ['frugal', 'balanced', 'quality'] },
  { path: 'economy.terse_system_prompt', value: false, isBoolean: true },
  { path: 'economy.prefer_batched_reads', value: false, isBoolean: true },
  // repo index
  { path: 'repo_index.enabled', value: false, isBoolean: true },
  { path: 'repo_index.auto_index_on_start', value: false, isBoolean: true },
  // tasks
  { path: 'tasks.enabled', value: true, isBoolean: true },
  { path: 'tasks.auto_start_read_only', value: true, isBoolean: true },
];

let _allOptions = []; // stored for search filtering

export async function initSettings() {
  const sidebar = document.querySelector('.settings-sidebar');
  const content = document.getElementById('settings-content');
  // search bar at top of sidebar
  const searchBox = document.createElement('input');
  searchBox.type = 'text';
  searchBox.className = 'settings-search';
  searchBox.placeholder = 'Search settings...';
  searchBox.addEventListener('input', () => {
    const q = searchBox.value.trim().toLowerCase();
    if (!q) {
      renderOptions(content, _allOptions);
      return;
    }
    const filtered = _allOptions.filter(o =>
      o.path.toLowerCase().includes(q) ||
      (o.path.split('.').pop() || '').replace(/_/g, ' ').includes(q)
    );
    renderOptions(content, filtered);
  });
  sidebar.appendChild(searchBox);
  // build category nav
  for (const [name] of Object.entries(categories)) {
    const el = document.createElement('div');
    el.className = 'settings-cat';
    el.textContent = name;
    el.addEventListener('click', () => {
      document.querySelectorAll('.settings-cat').forEach(c => c.classList.remove('active'));
      el.classList.add('active');
      searchBox.value = ''; // clear search on category click
      renderOptions(content, _allOptions);
      setTimeout(() => {
        const target = content.querySelector(`[data-category="${name}"]`);
        if (target) target.scrollIntoView({ behavior: 'smooth' });
      }, 50);
    });
    sidebar.appendChild(el);
  }
  // frontend-only options (not in backend config)
  const frontendOnly = [
    { path: 'ui.crt_effect', value: document.documentElement.classList.contains('crt'), isBoolean: true },
  ];
  _allOptions = defaultOptions;
  renderOptions(content, _allOptions); // render defaults immediately
  rpc('list_config_options', {}).then(result => { // update from backend if available
    const options = result.options || result || [];
    if (options.length) {
      // merge frontend-only options that backend doesn't know about
      const paths = new Set(options.map(o => o.path));
      for (const fo of frontendOnly) {
        if (!paths.has(fo.path)) options.push(fo);
      }
      _allOptions = options;
      renderOptions(content, _allOptions);
    }
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
        ${hasKey ? '<button class="btn btn-sm api-key-remove" title="Remove">Remove</button>' : ''}
      </div>`;
    const input = row.querySelector('.api-key-input');
    row.querySelector('.api-key-toggle').addEventListener('click', () => {
      input.type = input.type === 'password' ? 'text' : 'password';
    });
    // auto-save on input (debounced)
    let keyTimer;
    input.addEventListener('input', () => {
      clearTimeout(keyTimer);
      keyTimer = setTimeout(() => {
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
        if (!row.querySelector('.api-key-remove')) {
          const rm = document.createElement('button');
          rm.className = 'btn btn-sm api-key-remove';
          rm.title = 'Remove';
          rm.textContent = 'Remove';
          rm.addEventListener('click', () => removeKey(def, row, stored));
          row.querySelector('.api-key-actions').appendChild(rm);
        }
        showSaveIndicator(`api.${def.id}`);
      }, 600);
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
  rpc('set_api_key', { provider: def.id, apiKey: '', persist: true, reloadActiveProvider: true }).catch(() => {});
  const dot = row.querySelector('.api-key-status');
  dot.classList.remove('set');
  dot.title = 'No key configured';
  row.querySelector('.api-key-input').placeholder = 'Paste API key...';
  const rm = row.querySelector('.api-key-remove');
  if (rm) rm.remove();
}

// --- font customisation ---
const FONT_STORAGE_KEY = 'poor-cli-custom-fonts';
function getStoredFonts() { return JSON.parse(localStorage.getItem(FONT_STORAGE_KEY) || '{}'); }
function saveStoredFonts(obj) { localStorage.setItem(FONT_STORAGE_KEY, JSON.stringify(obj)); }

function parseFontFamily(url) { // extract family name from Google Fonts URL
  try {
    const u = new URL(url);
    const family = u.searchParams.get('family');
    if (!family) return null;
    return family.split(':')[0].replace(/\+/g, ' ');
  } catch { return null; }
}

function isGoogleFontsUrl(url) {
  try { return new URL(url).hostname.endsWith('googleapis.com'); }
  catch { return false; }
}

function injectFontLink(id, url) { // inject or replace a <link> for the font
  let link = document.getElementById(id);
  if (!url) { if (link) link.remove(); return; }
  if (!link) { link = document.createElement('link'); link.id = id; link.rel = 'stylesheet'; document.head.appendChild(link); }
  link.href = url;
}

export function applyCustomFonts() { // call on startup
  // restore CRT effect from localStorage
  if (localStorage.getItem('poor-cli-crt') === '1') document.documentElement.classList.add('crt');
  const fonts = getStoredFonts();
  if (fonts.uiUrl) {
    injectFontLink('custom-font-ui', fonts.uiUrl);
    const name = parseFontFamily(fonts.uiUrl);
    if (name) document.documentElement.style.setProperty('--font-sans', `'${name}', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`);
  }
  if (fonts.codeUrl) {
    injectFontLink('custom-font-code', fonts.codeUrl);
    const name = parseFontFamily(fonts.codeUrl);
    if (name) document.documentElement.style.setProperty('--font-mono', `'${name}', 'JetBrains Mono', 'Fira Code', monospace`);
  }
  if (fonts.displayUrl) {
    injectFontLink('custom-font-display', fonts.displayUrl);
    const name = parseFontFamily(fonts.displayUrl);
    if (name) document.documentElement.style.setProperty('--font-display', `'${name}', 'Syne', var(--font-sans)`);
  }
  if (fonts.uiSize) document.documentElement.style.setProperty('--font-size-ui', `${fonts.uiSize}px`);
  if (fonts.codeSize) document.documentElement.style.setProperty('--font-size-code', `${fonts.codeSize}px`);
}

function renderFontsGroup() {
  const group = document.createElement('div');
  group.className = 'settings-group';
  group.dataset.category = 'Fonts';
  group.innerHTML = '<h2>Fonts</h2>';
  const fonts = getStoredFonts();
  const defs = [
    { key: 'uiUrl', label: 'UI Font', hint: 'Google Fonts URL for interface text', placeholder: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap' },
    { key: 'codeUrl', label: 'Code Font', hint: 'Google Fonts URL for code snippets', placeholder: 'https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&display=swap' },
    { key: 'displayUrl', label: 'Display Font', hint: 'Google Fonts URL for headings & brand text', placeholder: 'https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&display=swap' },
  ];
  const sizeDefs = [
    { key: 'uiSize', label: 'UI Font Size', cssVar: '--font-size-ui', fallback: 14, min: 10, max: 24 },
    { key: 'codeSize', label: 'Code Font Size', cssVar: '--font-size-code', fallback: 13, min: 8, max: 24 },
  ];
  for (const def of defs) {
    const row = document.createElement('div');
    row.className = 'settings-row font-row';
    const cur = fonts[def.key] || '';
    const curName = cur ? (parseFontFamily(cur) || '') : '';
    row.innerHTML = `
      <div class="settings-row-info">
        <label>${def.label}${curName ? ` <span class="font-active-name">${curName}</span>` : ''}</label>
        <div class="desc">${def.hint}</div>
      </div>
      <div class="font-actions">
        <input type="text" class="font-url-input" value="${cur}" placeholder="${def.placeholder}" />
        <button class="btn btn-sm btn-primary font-save">Apply</button>
        ${cur ? '<button class="btn btn-sm font-reset">Reset</button>' : ''}
      </div>`;
    // auto-apply on input with debounce
    let fontTimer;
    const fontInput = row.querySelector('.font-url-input');
    const applyFont = () => {
      const url = fontInput.value.trim();
      if (url && !isGoogleFontsUrl(url)) return;
      fonts[def.key] = url;
      saveStoredFonts(fonts);
      applyCustomFonts();
    };
    fontInput.addEventListener('input', () => { clearTimeout(fontTimer); fontTimer = setTimeout(applyFont, 800); });
    row.querySelector('.font-save').addEventListener('click', () => { applyFont(); });
    const resetBtn = row.querySelector('.font-reset');
    if (resetBtn) resetBtn.addEventListener('click', () => {
      delete fonts[def.key];
      saveStoredFonts(fonts);
      const linkId = def.key === 'uiUrl' ? 'custom-font-ui' : def.key === 'codeUrl' ? 'custom-font-code' : 'custom-font-display';
      const cssVar = def.key === 'uiUrl' ? '--font-sans' : def.key === 'codeUrl' ? '--font-mono' : '--font-display';
      injectFontLink(linkId, null);
      document.documentElement.style.removeProperty(cssVar);
      renderOptions(document.getElementById('settings-content'), defaultOptions);
    });
    group.appendChild(row);
  }
  for (const sd of sizeDefs) {
    const row = document.createElement('div');
    row.className = 'settings-row';
    const cur = fonts[sd.key] || sd.fallback;
    row.innerHTML = `
      <div class="settings-row-info">
        <label>${sd.label}</label>
        <div class="desc">${sd.min}px – ${sd.max}px</div>
      </div>
      <div class="font-size-control">
        <input type="range" min="${sd.min}" max="${sd.max}" value="${cur}" class="font-size-range" />
        <span class="font-size-value">${cur}px</span>
      </div>`;
    const range = row.querySelector('.font-size-range');
    const label = row.querySelector('.font-size-value');
    range.addEventListener('input', () => {
      label.textContent = `${range.value}px`;
      document.documentElement.style.setProperty(sd.cssVar, `${range.value}px`);
    });
    range.addEventListener('change', () => {
      fonts[sd.key] = parseInt(range.value, 10);
      saveStoredFonts(fonts);
    });
    group.appendChild(row);
  }
  return group;
}

const LIGHT_THEMES = ['github-light', 'quiet-light', 'solarized-light', 'gruvbox-light', 'rose-pine-dawn', 'catppuccin-latte'];
const DARK_THEMES = ['one-dark', 'dracula', 'github-dark', 'monokai', 'nord', 'gruvbox-dark', 'rose-pine', 'catppuccin-mocha', 'tokyo-night'];

function renderThemeGroup(currentTheme) {
  const group = document.createElement('div');
  group.className = 'settings-group';
  group.dataset.category = 'Appearance';
  group.innerHTML = '<h2>Appearance</h2>';
  const isDark = DARK_THEMES.includes(currentTheme);
  // light/dark toggle
  const modeRow = document.createElement('div');
  modeRow.className = 'settings-row';
  modeRow.innerHTML = `<div class="settings-row-info"><label>Mode</label><div class="desc">Switch between light and dark mode</div></div>`;
  const modeToggle = document.createElement('div');
  modeToggle.className = 'theme-mode-toggle';
  modeToggle.innerHTML = `<button class="theme-mode-btn${!isDark ? ' active' : ''}" data-mode="light">Light</button>`
    + `<button class="theme-mode-btn${isDark ? ' active' : ''}" data-mode="dark">Dark</button>`;
  modeRow.appendChild(modeToggle);
  group.appendChild(modeRow);
  // theme picker
  const themeRow = document.createElement('div');
  themeRow.className = 'settings-row';
  themeRow.innerHTML = `<div class="settings-row-info"><label>Theme</label><div class="desc">ui.theme</div></div>`;
  const themeGrid = document.createElement('div');
  themeGrid.className = 'theme-grid';
  themeGrid.id = 'theme-grid';
  const themes = isDark ? DARK_THEMES : LIGHT_THEMES;
  themes.forEach(t => {
    const btn = document.createElement('button');
    btn.className = `theme-swatch${t === currentTheme ? ' active' : ''}`;
    btn.dataset.theme = t;
    btn.textContent = t.replace(/-/g, ' ');
    btn.addEventListener('click', () => {
      autoSave('ui.theme', t);
      applySettingImmediate('ui.theme', t);
      themeGrid.querySelectorAll('.theme-swatch').forEach(s => s.classList.toggle('active', s.dataset.theme === t));
    });
    themeGrid.appendChild(btn);
  });
  themeRow.appendChild(themeGrid);
  group.appendChild(themeRow);
  // wire mode toggle
  modeToggle.querySelectorAll('.theme-mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      modeToggle.querySelectorAll('.theme-mode-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const newThemes = btn.dataset.mode === 'dark' ? DARK_THEMES : LIGHT_THEMES;
      const first = newThemes[0];
      autoSave('ui.theme', first);
      applySettingImmediate('ui.theme', first);
      themeGrid.innerHTML = '';
      newThemes.forEach(t => {
        const sw = document.createElement('button');
        sw.className = `theme-swatch${t === first ? ' active' : ''}`;
        sw.dataset.theme = t;
        sw.textContent = t.replace(/-/g, ' ');
        sw.addEventListener('click', () => {
          autoSave('ui.theme', t);
          applySettingImmediate('ui.theme', t);
          themeGrid.querySelectorAll('.theme-swatch').forEach(s => s.classList.toggle('active', s.dataset.theme === t));
        });
        themeGrid.appendChild(sw);
      });
    });
  });
  return group;
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
  // appearance group (theme) first
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'github-light';
  container.appendChild(renderThemeGroup(currentTheme));
  // render in category order
  const orderedCats = Object.keys(categories);
  for (const cat of orderedCats) {
    if (cat === 'Fonts') { container.appendChild(renderFontsGroup()); continue; }
    if (cat === 'API Keys') { container.appendChild(renderApiKeysGroup()); continue; }
    const opts = grouped[cat];
    if (!opts) continue;
    // skip ui.theme — it's now in the Appearance group
    const filtered = opts.filter(o => o.path !== 'ui.theme');
    if (!filtered.length) continue;
    const group = document.createElement('div');
    group.className = 'settings-group';
    group.dataset.category = cat;
    group.innerHTML = `<h2>${cat}</h2>`;
    for (const opt of filtered) {
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
          autoSave(opt.path, e.target.checked);
          applySettingImmediate(opt.path, e.target.checked);
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
          autoSave(opt.path, sel.value);
          applySettingImmediate(opt.path, sel.value);
        });
        row.appendChild(sel);
      } else {
        const input = document.createElement('input');
        input.type = 'text';
        input.value = opt.value ?? '';
        let saveTimer;
        input.addEventListener('input', () => {
          clearTimeout(saveTimer);
          saveTimer = setTimeout(() => {
            const v = isNaN(input.value) ? input.value : Number(input.value);
            autoSave(opt.path, v);
            applySettingImmediate(opt.path, v);
          }, 500);
        });
        row.appendChild(input);
      }
      group.appendChild(row);
    }
    container.appendChild(group);
  }
}

function autoSave(path, value) {
  rpc('set_config', { keyPath: path, value }).catch(() => {});
  showSaveIndicator(path);
}

function showSaveIndicator(path) {
  // brief "saved" flash next to the setting
  const row = document.querySelector(`.settings-row .desc`);
  if (!row) return;
  const rows = document.querySelectorAll('.settings-row');
  for (const r of rows) {
    const desc = r.querySelector('.desc');
    if (desc && desc.textContent === path) {
      const existing = r.querySelector('.save-flash');
      if (existing) existing.remove();
      const flash = document.createElement('span');
      flash.className = 'save-flash';
      flash.textContent = 'saved';
      desc.appendChild(flash);
      setTimeout(() => flash.remove(), 1500);
      break;
    }
  }
}

function applySettingImmediate(path, value) {
  if (path === 'ui.theme') {
    document.documentElement.setAttribute('data-theme', value);
  } else if (path === 'ui.crt_effect') {
    document.documentElement.classList.toggle('crt', !!value);
    localStorage.setItem('poor-cli-crt', value ? '1' : '0');
  } else if (path === 'ui.tab_layout') {
    applyTabLayout(value);
  }
}

export function applyTabLayout(layout) {
  const hBar = document.getElementById('session-tab-bar');
  const vPanel = document.getElementById('vtabs-panel');
  if (layout === 'vertical') {
    if (hBar) hBar.hidden = true;
    if (vPanel) vPanel.hidden = false;
  } else {
    if (hBar) hBar.hidden = false;
    if (vPanel) vPanel.hidden = true;
  }
  localStorage.setItem('poor-cli-tab-layout', layout);
}

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
