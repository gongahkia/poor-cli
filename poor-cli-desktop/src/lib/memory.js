// memory management panel
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initMemory() {
  const container = document.getElementById('memory-content');
  if (!container) return;
  container.innerHTML = '';
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'search-input';
  searchInput.placeholder = 'Search memory...';
  container.appendChild(searchInput);
  const saveForm = document.createElement('div');
  saveForm.className = 'mem-save-form';
  saveForm.innerHTML = `<input type="text" class="mem-input mem-key" id="memory-key-input" placeholder="Key" />`
    + `<input type="text" class="mem-input mem-val" id="memory-val-input" placeholder="Value" />`
    + `<button class="btn btn-sm btn-primary" id="memory-save-btn">Save</button>`;
  container.appendChild(saveForm);
  const list = document.createElement('div');
  list.id = 'memory-list';
  list.className = 'item-list';
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
    const result = await rpc('get_config', {});
    const mem = result.memory || result.memories || null;
    if (!mem) { list.innerHTML = '<div class="view-empty"><p>No memories stored</p></div>'; return; }
    const items = Array.isArray(mem) ? mem : Object.entries(mem).map(([k, v]) => ({ key: k, value: v }));
    if (!items.length) { list.innerHTML = '<div class="view-empty"><p>No memories stored</p></div>'; return; }
    items.forEach(m => renderMemoryItem(m, list));
  } catch (_) {
    list.innerHTML = '<div class="view-empty"><p>Memory unavailable — backend not connected</p></div>';
  }
}

function renderMemoryItem(m, list) {
  const card = document.createElement('div');
  card.className = 'item-card';
  const key = m.key || m.name || m.id || '';
  const val = m.value || m.content || '';
  card.innerHTML = `<div class="item-card-header">`
    + `<h3>${esc(key)}</h3>`
    + `<button class="btn btn-sm btn-danger mem-del-btn">Delete</button>`
    + `</div>`
    + `<pre class="mem-value">${esc(typeof val === 'string' ? val : JSON.stringify(val, null, 2))}</pre>`;
  card.querySelector('.mem-del-btn').onclick = async () => {
    if (!confirm(`Delete memory "${key}"?`)) return;
    try {
      await rpc('set_config', { key_path: `memory.${key}`, value: null });
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
    const result = await rpc('get_config', {});
    const mem = result.memory || result.memories || {};
    const items = Array.isArray(mem) ? mem : Object.entries(mem).map(([k, v]) => ({ key: k, value: v }));
    const q = query.toLowerCase();
    const filtered = items.filter(m => ((m.key || m.name || '').toLowerCase().includes(q)) || (JSON.stringify(m.value || m.content || '').toLowerCase().includes(q)));
    if (!filtered.length) { list.innerHTML = '<div class="view-empty"><p>No results</p></div>'; return; }
    filtered.forEach(m => renderMemoryItem(m, list));
  } catch (e) { list.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`; }
}

async function saveMemory() {
  const key = document.getElementById('memory-key-input').value.trim();
  const val = document.getElementById('memory-val-input').value.trim();
  if (!key || !val) return;
  try {
    await rpc('set_config', { key_path: `memory.${key}`, value: val });
    document.getElementById('memory-key-input').value = '';
    document.getElementById('memory-val-input').value = '';
    await refreshMemory();
    addMessage(`Memory "${key}" saved.`, 'assistant');
  } catch (e) { addMessage(`Save failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
