// git view — status, log, diff, branches, tree
import { rpc } from './rpc.js';

let activeTab = 'status';

export async function initGit() {
  const content = document.getElementById('git-content');
  const tabs = document.querySelectorAll('.git-tab');
  tabs.forEach(t => {
    t.addEventListener('click', () => {
      tabs.forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      activeTab = t.dataset.tab;
      loadTab(activeTab);
    });
  });
  document.getElementById('git-refresh-btn').addEventListener('click', () => loadTab(activeTab));
  await loadTab('status');
}

async function loadTab(tab) {
  const content = document.getElementById('git-content');
  content.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
  try {
    if (tab === 'status') await renderStatus(content);
    else if (tab === 'log') await renderLog(content);
    else if (tab === 'diff') await renderDiff(content);
    else if (tab === 'branches') await renderBranches(content);
    else if (tab === 'tree') await renderTree(content);
  } catch (e) {
    content.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`;
  }
}

async function renderStatus(el) {
  const result = await rpc('git_status', {});
  const lines = (result.output || '').split('\n').filter(Boolean);
  if (!lines.length) { el.innerHTML = '<p style="color:var(--text-muted)">Not a git repository</p>'; return; }
  let html = '';
  const branch = lines[0].replace(/^## /, '');
  html += `<div class="git-branch-bar"><span class="git-branch-icon">&#x2387;</span> <strong>${esc(branch)}</strong></div>`;
  const files = lines.slice(1);
  if (!files.length) {
    html += '<p class="git-clean">Working tree clean</p>';
  } else {
    html += '<div class="git-file-list">';
    files.forEach(f => {
      const code = f.substring(0, 2);
      const path = f.substring(3);
      let cls = 'git-file-mod';
      if (code.includes('?')) cls = 'git-file-new';
      else if (code.includes('D')) cls = 'git-file-del';
      else if (code.includes('A')) cls = 'git-file-add';
      html += `<div class="git-file ${cls}"><span class="git-file-code">${esc(code)}</span><span class="git-file-path">${esc(path)}</span></div>`;
    });
    html += '</div>';
  }
  el.innerHTML = html;
}

async function renderLog(el) {
  const result = await rpc('git_log', { count: 30 });
  const out = result.output || '';
  if (!out.trim()) { el.innerHTML = '<p style="color:var(--text-muted)">No commits</p>'; return; }
  el.innerHTML = `<pre class="git-log-output">${esc(out)}</pre>`;
}

async function renderDiff(el) {
  const [unstaged, staged] = await Promise.all([
    rpc('git_diff', { staged: false }),
    rpc('git_diff', { staged: true }),
  ]);
  let html = '';
  const stagedOut = (staged.output || '').trim();
  const unstagedOut = (unstaged.output || '').trim();
  if (!stagedOut && !unstagedOut) {
    el.innerHTML = '<p style="color:var(--text-muted)">No changes</p>';
    return;
  }
  if (stagedOut) {
    html += '<h3 class="git-diff-heading">Staged</h3>';
    html += renderSideBySideDiff(stagedOut);
  }
  if (unstagedOut) {
    html += '<h3 class="git-diff-heading">Unstaged</h3>';
    html += renderSideBySideDiff(unstagedOut);
  }
  el.innerHTML = html;
}

function renderSideBySideDiff(raw) {
  // parse unified diff into per-file hunks, render side-by-side
  const files = raw.split(/^diff --git /m).filter(Boolean);
  let html = '';
  for (const file of files) {
    const lines = file.split('\n');
    const header = lines[0] || '';
    const match = header.match(/a\/(.+?) b\/(.+)/);
    const fname = match ? match[2] : header;
    html += `<div class="diff-file"><div class="diff-file-header">${esc(fname)}</div>`;
    html += '<div class="diff-side-by-side">';
    html += '<div class="diff-col diff-col-old"><div class="diff-col-label">Old</div>';
    html += '<table class="diff-table">';
    const oldLines = [];
    const newLines = [];
    let oldNum = 0, newNum = 0;
    for (const line of lines) {
      if (line.startsWith('@@')) {
        const m = line.match(/@@ -(\d+)/);
        if (m) oldNum = parseInt(m[1], 10) - 1;
        const m2 = line.match(/\+(\d+)/);
        if (m2) newNum = parseInt(m2[1], 10) - 1;
        oldLines.push({ num: '...', text: line, cls: 'diff-hunk' });
        newLines.push({ num: '...', text: line, cls: 'diff-hunk' });
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        oldNum++;
        oldLines.push({ num: oldNum, text: line.substring(1), cls: 'diff-del' });
      } else if (line.startsWith('+') && !line.startsWith('+++')) {
        newNum++;
        newLines.push({ num: newNum, text: line.substring(1), cls: 'diff-add' });
      } else if (!line.startsWith('diff') && !line.startsWith('index') && !line.startsWith('---') && !line.startsWith('+++')) {
        oldNum++; newNum++;
        oldLines.push({ num: oldNum, text: line.startsWith(' ') ? line.substring(1) : line, cls: '' });
        newLines.push({ num: newNum, text: line.startsWith(' ') ? line.substring(1) : line, cls: '' });
      }
    }
    // pad to same length
    while (oldLines.length < newLines.length) oldLines.push({ num: '', text: '', cls: 'diff-pad' });
    while (newLines.length < oldLines.length) newLines.push({ num: '', text: '', cls: 'diff-pad' });
    for (const l of oldLines) {
      html += `<tr class="${l.cls}"><td class="diff-num">${l.num}</td><td class="diff-code">${esc(l.text)}</td></tr>`;
    }
    html += '</table></div>';
    html += '<div class="diff-col diff-col-new"><div class="diff-col-label">New</div>';
    html += '<table class="diff-table">';
    for (const l of newLines) {
      html += `<tr class="${l.cls}"><td class="diff-num">${l.num}</td><td class="diff-code">${esc(l.text)}</td></tr>`;
    }
    html += '</table></div></div></div>';
  }
  return html;
}

async function renderBranches(el) {
  const result = await rpc('git_branches', {});
  const lines = (result.output || '').split('\n').filter(Boolean);
  if (!lines.length) { el.innerHTML = '<p style="color:var(--text-muted)">No branches</p>'; return; }
  let html = '<div class="git-branch-list">';
  lines.forEach(line => {
    const current = line.startsWith('*');
    const name = line.replace(/^\*?\s+/, '').trim();
    const isRemote = name.startsWith('remotes/');
    html += `<div class="git-branch-item${current ? ' git-branch-current' : ''}${isRemote ? ' git-branch-remote' : ''}">`
      + `<span class="git-branch-marker">${current ? '*' : ' '}</span>`
      + `<span>${esc(name)}</span></div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

async function renderTree(el) {
  // git log --graph --oneline --all --decorate
  let result;
  try {
    result = await rpc('execute_command', {
      command: 'git log --graph --oneline --all --decorate -40'
    });
  } catch {
    // fallback: try via git_log with graph format
    result = await rpc('git_log', { count: 40 });
  }
  const out = (result.output || result.stdout || '').trim();
  if (!out) { el.innerHTML = '<p style="color:var(--text-muted)">No commits</p>'; return; }
  // render with color coding for graph characters
  const lines = out.split('\n');
  let html = '<div class="git-tree">';
  for (const line of lines) {
    // color the graph part (everything before the commit hash)
    const graphMatch = line.match(/^([*|/\\ \-_.]+?)([a-f0-9]{7,}.*)?$/);
    if (graphMatch) {
      const graph = graphMatch[1] || '';
      const rest = graphMatch[2] || '';
      // highlight branch refs
      const coloredRest = esc(rest)
        .replace(/\(([^)]+)\)/g, '<span class="git-tree-ref">($1)</span>')
        .replace(/HEAD -&gt; (\S+)/g, '<span class="git-tree-head">HEAD → $1</span>');
      html += `<div class="git-tree-line"><span class="git-tree-graph">${esc(graph)}</span><span class="git-tree-msg">${coloredRest}</span></div>`;
    } else {
      html += `<div class="git-tree-line"><span class="git-tree-msg">${esc(line)}</span></div>`;
    }
  }
  html += '</div>';
  el.innerHTML = html;
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
