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
  container.innerHTML = '<p class="view-empty-text">Loading...</p>';
  try {
    const result = await rpc('get_config', {});
    const instructions = result.instructions || result.systemPrompt || null;
    container.innerHTML = '';
    if (!instructions) {
      container.innerHTML = '<div class="view-empty"><p>No active instructions</p></div>';
      return;
    }
    const layers = Array.isArray(instructions) ? instructions : [{ source: 'System', content: typeof instructions === 'string' ? instructions : JSON.stringify(instructions, null, 2) }];
    layers.forEach((layer, i) => {
      const card = document.createElement('div');
      card.className = 'item-card';
      const source = layer.source || layer.type || `Layer ${i}`;
      const content = layer.content || layer.text || layer.value || '';
      const preview = typeof content === 'string' ? content.slice(0, 200) : JSON.stringify(content).slice(0, 200);
      card.innerHTML = `<div class="item-card-header instr-header">`
        + `<h3>${esc(source)}</h3>`
        + `<span class="badge">${esc(layer.priority || layer.scope || '')}</span>`
        + `<span class="instr-toggle">expand</span>`
        + `</div>`
        + `<p class="item-card-meta">${esc(preview)}${content.length > 200 ? '...' : ''}</p>`
        + `<div class="instr-full" hidden><pre class="instr-pre">${esc(typeof content === 'string' ? content : JSON.stringify(content, null, 2))}</pre></div>`;
      const header = card.querySelector('.instr-header');
      const full = card.querySelector('.instr-full');
      const toggle = card.querySelector('.instr-toggle');
      header.onclick = () => {
        full.hidden = !full.hidden;
        toggle.textContent = full.hidden ? 'expand' : 'collapse';
      };
      container.appendChild(card);
    });
  } catch (e) {
    console.warn('[instructions] get_config:', e);
    container.innerHTML = '<div class="view-empty"><p>Instructions unavailable — backend not connected</p></div>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
