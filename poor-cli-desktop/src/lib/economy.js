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
    + `<select id="economy-preset-select" class="search-input" style="width:auto">`
    + PRESETS.map(p => `<option value="${p}">${p}</option>`).join('')
    + `</select>`;
  container.appendChild(summary);
  container.appendChild(savings);
  container.appendChild(presetDiv);
  document.getElementById('economy-preset-select').onchange = async (e) => {
    try {
      await rpc('poor-cli/setEconomyPreset', { preset: e.target.value });
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
    const cost = await rpc('poor-cli/getSessionCost', {});
    const tokens = cost.totalTokens || cost.tokens || 0;
    const usd = cost.estimatedCost || cost.cost || 0;
    const input = cost.inputTokens || 0;
    const output = cost.outputTokens || 0;
    summary.innerHTML = `<h3>Cost Summary</h3>`
      + `<div style="display:flex;gap:16px;flex-wrap:wrap">`
      + `<div><span style="color:var(--text-muted)">Total tokens</span><br><strong>${tokens.toLocaleString()}</strong></div>`
      + `<div><span style="color:var(--text-muted)">Input</span><br><strong>${input.toLocaleString()}</strong></div>`
      + `<div><span style="color:var(--text-muted)">Output</span><br><strong>${output.toLocaleString()}</strong></div>`
      + `<div><span style="color:var(--text-muted)">Est. cost</span><br><strong>$${usd.toFixed(4)}</strong></div>`
      + `</div>`;
  } catch (_) {
    summary.innerHTML = '<p style="color:var(--text-muted)">Cost data unavailable</p>';
  }
  try {
    const sv = await rpc('poor-cli/getEconomySavings', {});
    const items = sv.savings || sv.breakdown || sv || [];
    if (Array.isArray(items) && items.length) {
      savings.innerHTML = `<h3>Savings Breakdown</h3>` + items.map(s =>
        `<div style="display:flex;justify-content:space-between;padding:2px 0"><span>${esc(s.label || s.type || '')}</span><span style="color:var(--success)">-$${(s.saved || s.amount || 0).toFixed(4)}</span></div>`
      ).join('');
    } else {
      savings.innerHTML = `<h3>Savings</h3><p style="color:var(--text-muted)">No savings data</p>`;
    }
  } catch (_) {
    savings.innerHTML = '<h3>Savings</h3><p style="color:var(--text-muted)">Savings data unavailable</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
