// workflow templates view — grouped by category
import { rpc } from './rpc.js';
import { showView } from './views.js';

export async function initWorkflows() {
  const list = document.getElementById('workflows-list');
  list.innerHTML = '';
  let workflows;
  try {
    const result = await rpc('list_workflows', {});
    workflows = result.workflows || result || [];
  } catch (_) { workflows = []; }
  if (!workflows.length) return;

  // group by category
  const groups = {};
  for (const w of workflows) {
    const cat = w.category || 'General';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(w);
  }

  for (const [category, items] of Object.entries(groups)) {
    const section = document.createElement('div');
    section.className = 'wf-category';
    section.innerHTML = `<h3 class="wf-category-title">${esc(category)}</h3><div class="wf-grid"></div>`;
    const grid = section.querySelector('.wf-grid');
    for (const w of items) {
      const preset = w.preset || w.sandboxPreset || '';
      const title = w.title || w.name;
      const icon = w.icon || '';
      const card = document.createElement('div');
      card.className = 'wf-card';
      card.innerHTML = `
        <div class="wf-card-icon">${icon}</div>
        <div class="wf-card-body">
          <div class="wf-card-title">${esc(title)}</div>
          <div class="wf-card-desc">${esc(w.description || '')}</div>
        </div>
        <div class="wf-card-footer">
          ${preset ? `<span class="wf-preset-badge">${esc(preset)}</span>` : ''}
          <button class="btn btn-sm btn-primary wf-run-btn">Run</button>
        </div>`;
      card.querySelector('.wf-run-btn').onclick = () => runWorkflow(w.name);
      // clicking the card also runs
      card.addEventListener('click', (e) => {
        if (!e.target.classList.contains('wf-run-btn')) runWorkflow(w.name);
      });
      grid.appendChild(card);
    }
    list.appendChild(section);
  }
}

async function runWorkflow(name) {
  showView('chat');
  try {
    await rpc('send_chat', { message: `/${name}` });
  } catch (_) {}
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
