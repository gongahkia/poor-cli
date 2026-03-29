// prompt library — skills and custom commands browser
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initPromptLibrary() {
  const container = document.getElementById('prompt-library-content');
  if (!container) return;
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'search-input';
  searchInput.placeholder = 'Search prompts/skills...';
  const grid = document.createElement('div');
  grid.id = 'prompt-library-grid';
  grid.className = 'item-list';
  const preview = document.createElement('div');
  preview.id = 'prompt-library-preview';
  preview.className = 'item-card';
  preview.hidden = true;
  container.innerHTML = '';
  container.appendChild(searchInput);
  container.appendChild(grid);
  container.appendChild(preview);
  let allItems = [];
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.toLowerCase().trim();
    renderGrid(q ? allItems.filter(i => (i.name || '').toLowerCase().includes(q) || (i.description || '').toLowerCase().includes(q)) : allItems, grid, preview);
  });
  allItems = await loadItems();
  renderGrid(allItems, grid, preview);
}

async function loadItems() {
  const items = [];
  try {
    const skills = await rpc('poor-cli/listSkills', {});
    (skills.skills || skills || []).forEach(s => items.push({ ...s, _type: 'skill' }));
  } catch (_) {} // noncritical
  try {
    const cmds = await rpc('poor-cli/listCustomCommands', {});
    (cmds.commands || cmds || []).forEach(c => items.push({ ...c, _type: 'command' }));
  } catch (_) {} // noncritical
  return items;
}

function renderGrid(items, grid, preview) {
  grid.innerHTML = '';
  if (!items.length) { grid.innerHTML = '<p style="color:var(--text-muted)">No prompts found</p>'; return; }
  items.forEach(item => {
    const card = document.createElement('div');
    card.className = 'item-card';
    card.style.cursor = 'pointer';
    card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
      + `<h3>${esc(item.name || 'Untitled')}</h3>`
      + `<span class="badge">${esc(item._type)}</span>`
      + `</div>`
      + `<p style="font-size:12px;color:var(--text-muted)">${esc((item.description || item.prompt || '').slice(0, 100))}</p>`
      + `<button class="btn btn-sm btn-primary prompt-run-btn" style="margin-top:4px">Run</button>`;
    card.addEventListener('click', (e) => {
      if (e.target.classList.contains('prompt-run-btn')) return;
      showPreview(item, preview);
    });
    card.querySelector('.prompt-run-btn').onclick = () => runItem(item);
    grid.appendChild(card);
  });
}

function showPreview(item, preview) {
  preview.hidden = false;
  preview.innerHTML = `<h3>${esc(item.name || 'Untitled')}</h3>`
    + `<span class="badge">${esc(item._type)} ${item.source ? '| ' + esc(item.source) : ''}</span>`
    + `<pre style="white-space:pre-wrap;font-size:12px;margin-top:8px">${esc(item.prompt || item.content || item.description || JSON.stringify(item, null, 2))}</pre>`
    + `<button class="btn btn-sm btn-primary" id="preview-run-btn" style="margin-top:4px">Run</button>`;
  document.getElementById('preview-run-btn').onclick = () => runItem(item);
}

async function runItem(item) {
  try {
    if (item._type === 'skill') {
      const detail = await rpc('poor-cli/getSkill', { name: item.name });
      addMessage(`Skill "${item.name}": ${JSON.stringify(detail)}`, 'assistant');
    } else {
      await rpc('poor-cli/runCustomCommand', { name: item.name });
      addMessage(`Command "${item.name}" executed.`, 'assistant');
    }
  } catch (e) { addMessage(`Run failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
