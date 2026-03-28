/**
 * File/folder picker for poor-cli desktop.
 *
 * Shows pinned context files above the chat input, with an add button
 * that opens a searchable file browser modal for attaching files/folders.
 */

import { rpc } from './rpc.js';

let pinnedFiles = [];
let pickerOpen = false;
let searchResults = [];
let searchQuery = '';
let selectedIdx = 0;

export function initFilePicker() {
  const bar = document.getElementById('context-file-bar');
  const addBtn = document.getElementById('context-file-add');
  if (!bar || !addBtn) return;
  addBtn.addEventListener('click', openPicker);
  refreshPinnedFiles();
}

export async function refreshPinnedFiles() {
  const bar = document.getElementById('context-file-bar');
  const list = document.getElementById('context-file-list');
  if (!bar || !list) return;
  try {
    const result = await rpc('send_chat', { message: '/files' });
    const text = result?.response || '';
    // parse pinned files from response
    pinnedFiles = text.split('\n')
      .map(l => l.replace(/^[-•*]\s*/, '').trim())
      .filter(l => l && !l.startsWith('No ') && !l.startsWith('Pinned'));
  } catch { pinnedFiles = []; }
  renderPinnedFiles(list);
  bar.hidden = pinnedFiles.length === 0;
}

function renderPinnedFiles(container) {
  container.innerHTML = '';
  for (const f of pinnedFiles) {
    const chip = document.createElement('span');
    chip.className = 'context-file-chip';
    const name = f.split('/').pop();
    chip.innerHTML = `<span class="chip-name" title="${esc(f)}">${esc(name)}</span><span class="chip-remove" data-path="${esc(f)}">&times;</span>`;
    chip.querySelector('.chip-remove').onclick = (e) => {
      e.stopPropagation();
      removeFile(f);
    };
    container.appendChild(chip);
  }
}

async function removeFile(path) {
  try {
    await rpc('send_chat', { message: `/drop ${path}` });
  } catch {}
  await refreshPinnedFiles();
}

async function addFile(path) {
  try {
    await rpc('send_chat', { message: `/add ${path}` });
  } catch {}
  closePicker();
  await refreshPinnedFiles();
  // also insert @path into chat input
  const input = document.getElementById('chat-input');
  if (input) {
    const ref = path.includes(' ') ? `@"${path}"` : `@${path}`;
    input.value = input.value ? input.value + ' ' + ref : ref + ' ';
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
    searchInput.addEventListener('input', () => {
      searchQuery = searchInput.value;
      doSearch(searchQuery);
    });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closePicker(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); navigatePicker(1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); navigatePicker(-1); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (searchResults[selectedIdx]) addFile(searchResults[selectedIdx]);
        return;
      }
    });
  }
  overlay.classList.remove('hidden');
  pickerOpen = true;
  selectedIdx = 0;
  searchResults = [];
  const searchInput = overlay.querySelector('.fp-search');
  searchInput.value = '';
  searchInput.focus();
  overlay.querySelector('.fp-results').innerHTML = '<div class="fp-empty">Type to search for files and folders</div>';
}

function closePicker() {
  const overlay = document.getElementById('file-picker-overlay');
  if (overlay) overlay.classList.add('hidden');
  pickerOpen = false;
}

let searchDebounce = null;
async function doSearch(query) {
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = setTimeout(async () => {
    if (!query.trim()) {
      renderResults([]);
      return;
    }
    try {
      const result = await rpc('search_workspace_files', { query, limit: 20 });
      searchResults = result.files || [];
      renderResults(searchResults);
    } catch {
      searchResults = [];
      renderResults([]);
    }
  }, 200);
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
    html += `<div class="fp-item${sel}" data-idx="${i}">
      <span class="fp-item-icon">${f.endsWith('/') ? '📁' : '📄'}</span>
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
