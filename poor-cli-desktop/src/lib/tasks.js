// tasks view
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initTasks() {
  document.getElementById('create-task-btn').onclick = () => {
    document.getElementById('create-task-modal').hidden = false;
    document.getElementById('task-title-input').focus();
  };
  document.getElementById('task-modal-cancel').onclick = () => { document.getElementById('create-task-modal').hidden = true; };
  document.getElementById('task-modal-create').onclick = createTask;
  await refreshTasks();
}

async function refreshTasks() {
  const list = document.getElementById('tasks-list');
  list.innerHTML = '';
  try {
    const result = await rpc('list_tasks', {});
    const tasks = result.tasks || result || [];
    if (!tasks.length) { list.innerHTML = '<p style="color:var(--text-muted)">No tasks</p>'; return; }
    tasks.forEach(t => {
      const tid = t.taskId || t.id;
      const card = document.createElement('div');
      card.className = 'item-card';
      card.innerHTML = `<div class="task-card-header"><h3>${esc(t.title || tid || 'Untitled')}</h3><span class="badge">${esc(t.status || 'pending')}</span></div>`
        + `<p>${esc(t.prompt || t.description || '')}</p>`
        + `<div class="task-actions">`
        + (t.status === 'pending' || t.status === 'waiting_approval' ? `<button class="btn btn-sm btn-primary" data-act="start">Start</button>` : '')
        + (t.status === 'waiting_approval' ? `<button class="btn btn-sm btn-primary" data-act="approve">Approve</button>` : '')
        + (t.status === 'running' ? `<button class="btn btn-sm" data-act="cancel">Cancel</button>` : '')
        + (t.status === 'failed' ? `<button class="btn btn-sm" data-act="retry">Retry</button>` : '')
        + `</div>`;
      const startBtn = card.querySelector('[data-act="start"]');
      const approveBtn = card.querySelector('[data-act="approve"]');
      const cancelBtn = card.querySelector('[data-act="cancel"]');
      const retryBtn = card.querySelector('[data-act="retry"]');
      if (startBtn) startBtn.onclick = () => taskAction('start_task', tid);
      if (approveBtn) approveBtn.onclick = () => taskAction('approve_task', tid);
      if (cancelBtn) cancelBtn.onclick = () => taskAction('cancel_task', tid);
      if (retryBtn) retryBtn.onclick = () => taskAction('retry_task', tid);
      list.appendChild(card);
    });
  } catch (_) {
    list.innerHTML = '<p style="color:var(--text-muted)">Tasks unavailable — backend not connected</p>';
  }
}

async function taskAction(method, taskId) {
  try {
    await rpc(method, { task_id: taskId });
    await refreshTasks();
  } catch (e) { addMessage(`Task action failed: ${e}`, 'assistant'); }
}

async function createTask() {
  const title = document.getElementById('task-title-input').value.trim();
  const prompt = document.getElementById('task-prompt-input').value.trim();
  if (!title || !prompt) return;
  const sandbox = document.getElementById('task-sandbox-select').value;
  const approval = document.getElementById('task-approval-check').checked;
  document.getElementById('create-task-modal').hidden = true;
  try {
    await rpc('create_task', { title, prompt, sandbox_preset: sandbox || undefined, requires_approval: approval });
    await refreshTasks();
  } catch (e) { addMessage(`Task creation failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
