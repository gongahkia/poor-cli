// instruction stack inspector
import { rpc } from './rpc.js';

export async function initInstructions() {
  const container = document.getElementById('instructions-content');
  if (!container) return;
  await refreshInstructions();
}

export async function refreshInstructions() {
  const container = document.getElementById('instructions-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
  try {
    const result = await rpc('poor-cli/getInstructionStack', {});
    const layers = result.layers || result.stack || result.instructions || result || [];
    container.innerHTML = '';
    if (!layers.length) { container.innerHTML = '<p style="color:var(--text-muted)">No active instructions</p>'; return; }
    layers.forEach((layer, i) => {
      const card = document.createElement('div');
      card.className = 'item-card';
      const source = layer.source || layer.type || `Layer ${i}`;
      const content = layer.content || layer.text || layer.value || '';
      const preview = typeof content === 'string' ? content.slice(0, 200) : JSON.stringify(content).slice(0, 200);
      card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;cursor:pointer" class="instr-header">`
        + `<h3>${esc(source)}</h3>`
        + `<span class="badge">${esc(layer.priority || layer.scope || '')}</span>`
        + `<span class="instr-toggle" style="font-size:12px;color:var(--text-muted)">expand</span>`
        + `</div>`
        + `<p style="color:var(--text-muted);font-size:12px">${esc(preview)}${content.length > 200 ? '...' : ''}</p>`
        + `<div class="instr-full" hidden><pre style="white-space:pre-wrap;font-size:12px">${esc(typeof content === 'string' ? content : JSON.stringify(content, null, 2))}</pre></div>`;
      const header = card.querySelector('.instr-header');
      const full = card.querySelector('.instr-full');
      const toggle = card.querySelector('.instr-toggle');
      header.onclick = () => {
        full.hidden = !full.hidden;
        toggle.textContent = full.hidden ? 'expand' : 'collapse';
      };
      container.appendChild(card);
    });
  } catch (_) {
    container.innerHTML = '<p style="color:var(--text-muted)">Instructions unavailable — backend not connected</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
