// file changes panel — groups mutations by directory, renders status + stats
const panel = document.getElementById('file-changes-panel');
const body = document.getElementById('fcp-body');
const closeBtn = document.getElementById('fcp-close');
const diffPreview = document.getElementById('fcp-diff-preview');
const fcBtn = document.getElementById('wb-file-changes');
const fcCount = document.getElementById('wb-fc-count');
const fcAdded = document.getElementById('wb-fc-added');
const fcRemoved = document.getElementById('wb-fc-removed');

export function initFileChangesPanel() {
  closeBtn.addEventListener('click', closeFileChangesPanel);
}

export function toggleFileChangesPanel() {
  panel.classList.toggle('collapsed');
  fcBtn.classList.toggle('active', !panel.classList.contains('collapsed'));
}

export function openFileChangesPanel() {
  panel.classList.remove('collapsed');
  fcBtn.classList.add('active');
}

export function closeFileChangesPanel() {
  panel.classList.add('collapsed');
  fcBtn.classList.remove('active');
}

export function updateFileChanges(status) {
  const mutations = status.lastMutations || status.mutations || [];
  const changes = status.fileChanges || status.changes || {};
  if (!mutations.length && !changes.filesChanged) {
    fcBtn.hidden = true;
    return;
  }
  fcBtn.hidden = false;
  fcCount.textContent = changes.filesChanged || mutations.length;
  fcAdded.textContent = `+${changes.additions || 0}`;
  fcRemoved.textContent = `-${changes.deletions || 0}`;
  renderFileList(mutations, changes);
}

function renderFileList(mutations, changes) {
  body.innerHTML = '';
  diffPreview.hidden = true;
  if (!mutations.length) return;
  const groups = {};
  for (const m of mutations) {
    const parts = m.path.replace(/\\/g, '/').split('/');
    const fileName = parts.pop();
    const dir = parts.join('/') || '.';
    if (!groups[dir]) groups[dir] = [];
    groups[dir].push({ name: fileName, operation: m.operation || 'write', path: m.path });
  }
  const totalAdd = changes.additions || 0;
  const totalDel = changes.deletions || 0;
  const totalFiles = Object.values(groups).reduce((s, g) => s + g.length, 0);
  for (const [dir, files] of Object.entries(groups)) {
    const group = document.createElement('div');
    group.className = 'fcp-group';
    const header = document.createElement('div');
    header.className = 'fcp-group-header';
    header.innerHTML = `<span class="chevron">&#9662;</span><span class="fg-path">${dir}/</span><span class="fg-count">${files.length}</span>`;
    header.addEventListener('click', () => group.classList.toggle('collapsed'));
    group.appendChild(header);
    const filesDiv = document.createElement('div');
    filesDiv.className = 'fcp-group-files';
    for (const f of files) {
      const statusClass = f.operation === 'create' ? 'added' : f.operation === 'delete' ? 'deleted' : 'modified';
      const statusLabel = f.operation === 'create' ? 'A' : f.operation === 'delete' ? 'D' : 'M';
      const perFileAdd = totalFiles > 0 ? Math.round(totalAdd / totalFiles) : 0; // estimate per-file
      const perFileDel = totalFiles > 0 ? Math.round(totalDel / totalFiles) : 0;
      const total = perFileAdd + perFileDel || 1;
      const addPct = Math.round((perFileAdd / total) * 100);
      const delPct = 100 - addPct;
      const entry = document.createElement('div');
      entry.className = 'fcp-file';
      entry.innerHTML = `<span class="fcp-file-status ${statusClass}">${statusLabel}</span>` +
        `<span class="fcp-file-name" title="${f.path}">${f.name}</span>` +
        `<span class="fcp-file-stats"><span class="added">+${perFileAdd}</span> <span class="removed">-${perFileDel}</span></span>` +
        `<div class="fcp-proportion-bar"><div class="bar-added" style="width:${addPct}%"></div><div class="bar-removed" style="width:${delPct}%"></div></div>`;
      entry.addEventListener('click', () => {
        body.querySelectorAll('.fcp-file').forEach(el => el.classList.remove('selected'));
        entry.classList.add('selected');
        showDiffPreview(f);
      });
      filesDiv.appendChild(entry);
    }
    group.appendChild(filesDiv);
    body.appendChild(group);
  }
}

function showDiffPreview(file) {
  diffPreview.hidden = false;
  diffPreview.innerHTML = `<div class="diff-title">${file.name} — preview</div>` +
    `<div class="diff-ctx">  // diff data requires preview_mutation RPC</div>` +
    `<div class="diff-ctx">  // operation: ${file.operation}</div>` +
    `<div class="diff-ctx">  // path: ${file.path}</div>`;
}
