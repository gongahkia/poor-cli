// memory management panel
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initMemory() {
  const container = document.getElementById('memory-content');
  if (!container) return;
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'search-input';
  searchInput.placeholder = 'Search memory...';
  const saveForm = document.createElement('div');
  saveForm.className = 'memory-save-form';
  saveForm.innerHTML = `<input type="text" class="search-input" id="memory-key-input" placeholder="Key" style="width:30%;display:inline-block;margin-right:4px" />`
    + `<input type="text" class="search-input" id="memory-val-input" placeholder="Value" style="width:50%;display:inline-block;margin-right:4px" />`
    + `<button class="btn btn-sm btn-primary" id="memory-save-btn">Save</button>`;
  const list = document.createElement('div');
  list.id = 'memory-list';
  list.className = 'item-list';
  container.innerHTML = '';
  container.appendChild(searchInput);
  container.appendChild(saveForm);
  container.appendChild(list);
  searchInput.addEventListener('input', () => searchMemory(searchInput.value, list));
  document.getElementById('memory-save-btn').onclick = saveMemory;
  await refreshMemory(list);
}

async function refreshMemory(list) {
  list = list || document.getElementById('memory-list');
  if (!list) return;
  list.innerHTML = '';
  try {
    const result = await rpc('poor-cli/memoryList', {});
    const items = result.memories || result.items || result || [];
    if (!items.length) { list.innerHTML = '<p style="color:var(--text-muted)">No memories stored</p>'; return; }
    items.forEach(m => renderMemoryItem(m, list));
  } catch (_) {
    list.innerHTML = '<p style="color:var(--text-muted)">Memory unavailable — backend not connected</p>';
  }
}

function renderMemoryItem(m, list) {
  const card = document.createElement('div');
  card.className = 'item-card';
  const key = m.key || m.name || m.id || '';
  const val = m.value || m.content || '';
  card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
    + `<h3>${esc(key)}</h3>`
    + `<button class="btn btn-sm memory-del-btn" style="color:var(--error)">Delete</button>`
    + `</div>`
    + `<p style="font-family:monospace;font-size:12px;white-space:pre-wrap">${esc(typeof val === 'string' ? val : JSON.stringify(val, null, 2))}</p>`;
  card.querySelector('.memory-del-btn').onclick = async () => {
    if (!confirm(`Delete memory "${key}"?`)) return;
    try {
      await rpc('poor-cli/memoryDelete', { key });
      card.remove();
      addMessage(`Memory "${key}" deleted.`, 'assistant');
    } catch (e) { addMessage(`Delete failed: ${e}`, 'assistant'); }
  };
  list.appendChild(card);
}

async function searchMemory(query, list) {
  if (!query.trim()) { await refreshMemory(list); return; }
  list.innerHTML = '';
  try {
    const result = await rpc('poor-cli/memorySearch', { query: query.trim() });
    const items = result.memories || result.results || result || [];
    if (!items.length) { list.innerHTML = '<p style="color:var(--text-muted)">No results</p>'; return; }
    items.forEach(m => renderMemoryItem(m, list));
  } catch (e) { list.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`; }
}

async function saveMemory() {
  const key = document.getElementById('memory-key-input').value.trim();
  const val = document.getElementById('memory-val-input').value.trim();
  if (!key || !val) return;
  try {
    await rpc('poor-cli/memorySave', { key, value: val });
    document.getElementById('memory-key-input').value = '';
    document.getElementById('memory-val-input').value = '';
    await refreshMemory();
    addMessage(`Memory "${key}" saved.`, 'assistant');
  } catch (e) { addMessage(`Save failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
