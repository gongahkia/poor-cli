// settings page — fetches config options, renders categorized form
import { rpc } from './rpc.js';

const categories = { // display name -> config key prefix
  'General': 'ui',
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
  // fetch options
  try {
    const result = await rpc('list_config_options', {});
    const options = result.options || result || [];
    renderOptions(content, options);
  } catch (e) {
    content.innerHTML = `<p style="color:var(--error)">Failed to load config: ${e}</p>`;
  }
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
  for (const [cat, opts] of Object.entries(grouped)) {
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
