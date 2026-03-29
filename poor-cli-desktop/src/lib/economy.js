// economy dashboard — cost tracking and savings
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

const PRESETS = ['none', 'light', 'moderate', 'aggressive'];

export async function initEconomy() {
  const container = document.getElementById('economy-content');
  if (!container) return;
  container.innerHTML = '';
  const summary = document.createElement('div');
  summary.id = 'economy-summary';
  summary.className = 'item-card';
  const savings = document.createElement('div');
  savings.id = 'economy-savings';
  savings.className = 'item-card';
  const presetDiv = document.createElement('div');
  presetDiv.className = 'item-card';
  presetDiv.innerHTML = `<h3>Economy Preset</h3>`
    + `<select id="economy-preset-select" class="econ-select">`
    + PRESETS.map(p => `<option value="${p}">${p}</option>`).join('')
    + `</select>`;
  container.appendChild(summary);
  container.appendChild(savings);
  container.appendChild(presetDiv);
  document.getElementById('economy-preset-select').onchange = async (e) => {
    try {
      await rpc('set_config', { key_path: 'economy.preset', value: e.target.value });
      addMessage(`Economy preset set to "${e.target.value}".`, 'assistant');
    } catch (err) { addMessage(`Preset change failed: ${err}`, 'assistant'); }
  };
  await refreshEconomy();
}

export async function refreshEconomy() {
  const summary = document.getElementById('economy-summary');
  const savings = document.getElementById('economy-savings');
  if (!summary || !savings) return;
  try {
    const cost = await rpc('get_session_cost', {});
    const tokens = cost.totalTokens || cost.tokens || 0;
    const usd = cost.estimatedCost || cost.cost || 0;
    const input = cost.inputTokens || 0;
    const output = cost.outputTokens || 0;
    summary.innerHTML = `<h3>Cost Summary</h3>`
      + `<div class="econ-grid">`
      + `<div class="econ-stat"><span class="econ-label">Total tokens</span><strong>${tokens.toLocaleString()}</strong></div>`
      + `<div class="econ-stat"><span class="econ-label">Input</span><strong>${input.toLocaleString()}</strong></div>`
      + `<div class="econ-stat"><span class="econ-label">Output</span><strong>${output.toLocaleString()}</strong></div>`
      + `<div class="econ-stat"><span class="econ-label">Est. cost</span><strong>$${usd.toFixed(4)}</strong></div>`
      + `</div>`;
  } catch (_) {
    summary.innerHTML = '<div class="view-empty"><p>Cost data unavailable</p></div>';
  }
  try {
    const sv = await rpc('get_config', {});
    const preset = sv.economy?.preset || sv.economyPreset || 'none';
    const sel = document.getElementById('economy-preset-select');
    if (sel) sel.value = preset;
  } catch (_) {}
  savings.innerHTML = '<h3>Savings</h3><p class="view-empty-text">Savings data tracked per session</p>';
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
