// workflow templates view
import { rpc } from './rpc.js';
import { showView } from './views.js';

const FALLBACK_WORKFLOWS = [
  { name: 'review', description: 'Code review — find bugs, regressions, missing tests', preset: 'review-only' },
  { name: 'debug', description: 'Diagnose failures — find root cause, suggest minimal fix', preset: 'review-only' },
  { name: 'implement', description: 'Feature implementation — scoped changes with tests', preset: 'workspace-write' },
  { name: 'summarize', description: 'Explain repository or area — architecture, behavior', preset: 'read-only' },
  { name: 'qa', description: 'QA health check — breaking changes, next steps', preset: 'review-only' },
];

export async function initWorkflows() {
  const list = document.getElementById('workflows-list');
  list.innerHTML = '';
  let workflows;
  try {
    const result = await rpc('list_workflows', {});
    workflows = result.workflows || result || [];
    if (!workflows.length) workflows = FALLBACK_WORKFLOWS;
  } catch (_) {
    workflows = FALLBACK_WORKFLOWS;
  }
  workflows.forEach(w => {
    const card = document.createElement('div');
    card.className = 'item-card workflow-card';
    const preset = w.preset || w.sandboxPreset || '';
    const title = w.title || w.name;
    card.innerHTML = `<div class="wf-card-header"><h3>${esc(title)}</h3>${preset ? `<span class="badge wf-preset">${esc(preset)}</span>` : ''}</div>`
      + `<p>${esc(w.description || '')}</p>`
      + `<div class="wf-actions"><button class="btn btn-sm btn-primary wf-run-btn">Run</button></div>`;
    card.querySelector('.wf-run-btn').onclick = () => runWorkflow(w.name);
    list.appendChild(card);
  });
}

async function runWorkflow(name) {
  showView('chat');
  try {
    await rpc('send_chat', { message: `/${name}` });
  } catch (_) {} // result handled by chat view
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
