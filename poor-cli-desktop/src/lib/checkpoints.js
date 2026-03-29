// checkpoints view
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initCheckpoints() {
  document.getElementById('create-checkpoint-btn').onclick = async () => {
    const desc = prompt('Checkpoint description:');
    if (desc === null) return;
    try {
      await rpc('create_checkpoint', { description: desc || 'Manual checkpoint' });
      await refreshCheckpoints();
    } catch (e) { addMessage(`Checkpoint failed: ${e}`, 'assistant'); }
  };
  await refreshCheckpoints();
}

async function refreshCheckpoints() {
  const list = document.getElementById('checkpoints-list');
  list.innerHTML = '';
  try {
    const result = await rpc('list_checkpoints', {});
    const cps = result.checkpoints || result || [];
    if (!cps.length) { list.innerHTML = '<p style="color:var(--text-muted)">No checkpoints</p>'; return; }
    cps.forEach(cp => {
      const cid = cp.checkpointId || cp.id;
      const card = document.createElement('div');
      card.className = 'item-card';
      card.innerHTML = `<h3>${esc(cp.description || cid || 'Untitled')}</h3>`
        + `<p style="color:var(--text-muted);font-size:12px">${esc(cp.createdAt || '')}</p>`
        + `<div class="checkpoint-actions">`
        + `<button class="btn btn-sm" data-act="preview">Preview</button>`
        + `<button class="btn btn-sm btn-primary" data-act="restore">Restore</button>`
        + `</div>`;
      card.querySelector('[data-act="preview"]').onclick = () => previewCheckpoint(cid);
      card.querySelector('[data-act="restore"]').onclick = () => restoreCheckpoint(cid);
      list.appendChild(card);
    });
  } catch (_) {
    list.innerHTML = '<p style="color:var(--text-muted)">Checkpoints unavailable — backend not connected</p>';
  }
}

async function previewCheckpoint(id) {
  const panel = document.getElementById('checkpoint-preview');
  panel.hidden = false;
  panel.innerHTML = '<p>Loading...</p>';
  try {
    const result = await rpc('preview_checkpoint', { checkpoint_id: id });
    panel.innerHTML = `<pre>${esc(JSON.stringify(result, null, 2))}</pre>`;
  } catch (e) { panel.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`; }
}

async function restoreCheckpoint(id) {
  if (!confirm('Restore this checkpoint? Current changes may be lost.')) return;
  try {
    await rpc('restore_checkpoint', { checkpoint_id: id });
    addMessage('Checkpoint restored.', 'assistant');
    await refreshCheckpoints();
  } catch (e) { addMessage(`Restore failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
