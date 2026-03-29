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
    if (!tasks.length) { list.innerHTML = '<div class="view-empty"><p>No tasks yet</p></div>'; return; }
    tasks.forEach(t => {
      const tid = t.taskId || t.id;
      const status = t.status || 'pending';
      const card = document.createElement('div');
      card.className = 'item-card task-card';
      // status badge styling
      const badgeCls = status === 'completed' || status === 'success' ? 'badge-ok'
        : status === 'failed' || status === 'error' ? 'badge-fail'
        : status === 'running' ? 'badge-warn'
        : status === 'awaiting_approval' || status === 'waiting_approval' ? 'badge-warn'
        : '';
      card.innerHTML = `<div class="item-card-header">`
        + `<h3>${esc(t.title || tid || 'Untitled')}</h3>`
        + `<span class="badge ${badgeCls}">${esc(status)}</span>`
        + `</div>`
        + `<p class="item-card-meta">${esc(t.prompt || t.description || '')}</p>`
        + `<div class="task-detail" hidden></div>`
        + `<div class="item-card-actions">`
        + `<button class="btn btn-sm" data-act="view">View</button>`
        + (status === 'pending' || status === 'awaiting_approval' || status === 'waiting_approval' ? `<button class="btn btn-sm btn-primary" data-act="start">Start</button>` : '')
        + (status === 'awaiting_approval' || status === 'waiting_approval' ? `<button class="btn btn-sm btn-primary" data-act="approve">Approve</button>` : '')
        + (status === 'running' ? `<button class="btn btn-sm" data-act="cancel">Cancel</button>` : '')
        + (status === 'failed' || status === 'error' ? `<button class="btn btn-sm" data-act="retry">Retry</button>` : '')
        + (status === 'completed' || status === 'success' ? `<button class="btn btn-sm" data-act="replay">Replay</button>` : '')
        + `<button class="btn btn-sm btn-danger" data-act="delete">Delete</button>`
        + `</div>`;
      // wire buttons
      const viewBtn = card.querySelector('[data-act="view"]');
      const detail = card.querySelector('.task-detail');
      viewBtn.onclick = async () => {
        if (!detail.hidden) { detail.hidden = true; viewBtn.textContent = 'View'; return; }
        detail.innerHTML = '<p class="view-empty-text">Loading...</p>';
        detail.hidden = false;
        viewBtn.textContent = 'Hide';
        try {
          const data = await rpc('get_task', { task_id: tid });
          const task = data.task || data;
          detail.innerHTML = `<pre class="task-output">${esc(JSON.stringify(task, null, 2))}</pre>`;
        } catch (e) { detail.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`; }
      };
      const startBtn = card.querySelector('[data-act="start"]');
      const approveBtn = card.querySelector('[data-act="approve"]');
      const cancelBtn = card.querySelector('[data-act="cancel"]');
      const retryBtn = card.querySelector('[data-act="retry"]');
      const replayBtn = card.querySelector('[data-act="replay"]');
      const deleteBtn = card.querySelector('[data-act="delete"]');
      if (startBtn) startBtn.onclick = () => taskAction('start_task', tid);
      if (approveBtn) approveBtn.onclick = () => taskAction('approve_task', tid);
      if (cancelBtn) cancelBtn.onclick = () => taskAction('cancel_task', tid);
      if (retryBtn) retryBtn.onclick = () => taskAction('retry_task', tid);
      if (replayBtn) replayBtn.onclick = () => taskAction('replay_task', tid);
      if (deleteBtn) deleteBtn.onclick = async () => {
        if (!confirm(`Delete task "${t.title || tid}"?`)) return;
        try {
          await rpc('cancel_task', { task_id: tid });
          card.remove();
        } catch (e) { addMessage(`Delete failed: ${e}`, 'assistant'); }
      };
      list.appendChild(card);
    });
  } catch (_) {
    list.innerHTML = '<div class="view-empty"><p>Tasks unavailable — backend not connected</p></div>';
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
