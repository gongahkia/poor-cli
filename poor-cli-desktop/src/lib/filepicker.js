/**
 * File/folder picker for poor-cli desktop.
 *
 * Always-visible bar above chat input with pinned context file chips
 * and a + button that opens a searchable file browser modal.
 */

import { rpc } from './rpc.js';

let pinnedFiles = []; // local tracking of @-attached files
let searchResults = [];
let selectedIdx = 0;

export function initFilePicker() {
  const addBtn = document.getElementById('context-file-add');
  if (!addBtn) return;
  addBtn.addEventListener('click', openPicker);
  // always show the bar (it has the + button)
  const bar = document.getElementById('context-file-bar');
  if (bar) bar.hidden = false;
  renderChips();
}

function renderChips() {
  const list = document.getElementById('context-file-list');
  if (!list) return;
  list.innerHTML = '';
  for (const f of pinnedFiles) {
    const chip = document.createElement('span');
    chip.className = 'context-file-chip';
    const name = f.split('/').pop();
    chip.innerHTML = `<span class="chip-name" title="${esc(f)}">${esc(name)}</span><span class="chip-remove">&times;</span>`;
    chip.querySelector('.chip-remove').onclick = (e) => {
      e.stopPropagation();
      pinnedFiles = pinnedFiles.filter(p => p !== f);
      renderChips();
    };
    list.appendChild(chip);
  }
}

export function getPinnedFiles() {
  return [...pinnedFiles];
}

function addFile(path) {
  if (!pinnedFiles.includes(path)) {
    pinnedFiles.push(path);
    renderChips();
  }
  closePicker();
  // insert @path into chat input
  const input = document.getElementById('chat-input');
  if (input) {
    const ref = path.includes(' ') ? `@"${path}"` : `@${path}`;
    const cur = input.value;
    input.value = cur ? cur + ' ' + ref : ref + ' ';
    input.focus();
  }
}

function openPicker() {
  let overlay = document.getElementById('file-picker-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'file-picker-overlay';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="file-picker-modal">
        <div class="fp-header">
          <h3>Add File or Folder</h3>
          <button class="fp-close">&times;</button>
        </div>
        <input class="fp-search" type="text" placeholder="Search files..." autofocus />
        <div class="fp-results"></div>
        <div class="fp-hint">Type to search. Enter to add. Esc to close.</div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('.fp-close').onclick = closePicker;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closePicker(); });
    const searchInput = overlay.querySelector('.fp-search');
    let debounce;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => doSearch(searchInput.value), 200);
    });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closePicker(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); navigatePicker(1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); navigatePicker(-1); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        if (searchResults[selectedIdx]) addFile(searchResults[selectedIdx]);
        return;
      }
    });
  }
  overlay.classList.remove('hidden');
  overlay.style.display = '';
  selectedIdx = 0;
  searchResults = [];
  const searchInput = overlay.querySelector('.fp-search');
  searchInput.value = '';
  searchInput.focus();
  overlay.querySelector('.fp-results').innerHTML = '<div class="fp-empty">Type to search for files and folders</div>';
}

function closePicker() {
  const overlay = document.getElementById('file-picker-overlay');
  if (overlay) { overlay.classList.add('hidden'); overlay.style.display = 'none'; }
}

async function doSearch(query) {
  if (!query.trim()) {
    searchResults = [];
    renderResults([]);
    return;
  }
  try {
    const result = await rpc('search_workspace_files', { query, limit: 20 });
    searchResults = result.files || [];
  } catch {
    // fallback: try glob via executeCommand
    try {
      const result = await rpc('poor-cli/executeCommand', {
        command: `find . -maxdepth 4 -name "*${query.replace(/[^a-zA-Z0-9._-]/g, '')}*" -not -path "*/.*" 2>/dev/null | head -20`
      });
      const out = (result.output || result.stdout || '').trim();
      searchResults = out ? out.split('\n').map(f => f.replace(/^\.\//, '')) : [];
    } catch { searchResults = []; }
  }
  renderResults(searchResults);
}

function renderResults(files) {
  const container = document.querySelector('.fp-results');
  if (!container) return;
  if (!files.length) {
    container.innerHTML = '<div class="fp-empty">No files found</div>';
    return;
  }
  selectedIdx = Math.min(selectedIdx, files.length - 1);
  let html = '';
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const name = f.split('/').pop();
    const dir = f.includes('/') ? f.substring(0, f.lastIndexOf('/')) : '';
    const sel = i === selectedIdx ? ' fp-selected' : '';
    const isDir = f.endsWith('/');
    html += `<div class="fp-item${sel}" data-idx="${i}">
      <span class="fp-item-name">${esc(name)}</span>
      <span class="fp-item-path">${esc(dir)}</span>
    </div>`;
  }
  container.innerHTML = html;
  container.querySelectorAll('.fp-item').forEach(el => {
    el.onclick = () => addFile(files[parseInt(el.dataset.idx)]);
  });
}

function navigatePicker(dir) {
  if (!searchResults.length) return;
  selectedIdx = (selectedIdx + dir + searchResults.length) % searchResults.length;
  renderResults(searchResults);
  const sel = document.querySelector('.fp-selected');
  if (sel) sel.scrollIntoView({ block: 'nearest' });
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
