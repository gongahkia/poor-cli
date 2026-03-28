// git view — status, log, diff, branches, tree
import { rpc } from './rpc.js';

let activeTab = 'status';

export async function initGit() {
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

// log tab: --graph --oneline --all with colored graph chars
async function renderLog(el) {
  let result;
  try {
    result = await rpc('poor-cli/executeCommand', {
      command: 'git log --graph --oneline --all --decorate -50'
    });
  } catch {
    result = await rpc('git_log', { count: 50 });
  }
  const out = (result.output || result.stdout || '').trim();
  if (!out) { el.innerHTML = '<p style="color:var(--text-muted)">No commits</p>'; return; }
  const lines = out.split('\n');
  let html = '<div class="git-tree">';
  for (const line of lines) {
    const graphMatch = line.match(/^([*|/\\ \-_.]+?)([a-f0-9]{7,}.*)?$/);
    if (graphMatch) {
      const graph = graphMatch[1] || '';
      const rest = graphMatch[2] || '';
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
  const files = raw.split(/^diff --git /m).filter(Boolean);
  let html = '';
  for (const file of files) {
    const lines = file.split('\n');
    const header = lines[0] || '';
    const match = header.match(/a\/(.+?) b\/(.+)/);
    const fname = match ? match[2] : header;
    html += `<div class="diff-file"><div class="diff-file-header">${esc(fname)}</div>`;
    html += '<div class="diff-side-by-side">';
    html += '<div class="diff-col diff-col-old"><div class="diff-col-label">Old</div><table class="diff-table">';
    const oldLines = [], newLines = [];
    let oldNum = 0, newNum = 0;
    for (const line of lines) {
      if (line.startsWith('@@')) {
        const m = line.match(/@@ -(\d+)/); if (m) oldNum = parseInt(m[1], 10) - 1;
        const m2 = line.match(/\+(\d+)/); if (m2) newNum = parseInt(m2[1], 10) - 1;
        oldLines.push({ num: '...', text: line, cls: 'diff-hunk' });
        newLines.push({ num: '...', text: line, cls: 'diff-hunk' });
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        oldNum++; oldLines.push({ num: oldNum, text: line.substring(1), cls: 'diff-del' });
      } else if (line.startsWith('+') && !line.startsWith('+++')) {
        newNum++; newLines.push({ num: newNum, text: line.substring(1), cls: 'diff-add' });
      } else if (!line.startsWith('diff') && !line.startsWith('index') && !line.startsWith('---') && !line.startsWith('+++')) {
        oldNum++; newNum++;
        oldLines.push({ num: oldNum, text: line.startsWith(' ') ? line.substring(1) : line, cls: '' });
        newLines.push({ num: newNum, text: line.startsWith(' ') ? line.substring(1) : line, cls: '' });
      }
    }
    while (oldLines.length < newLines.length) oldLines.push({ num: '', text: '', cls: 'diff-pad' });
    while (newLines.length < oldLines.length) newLines.push({ num: '', text: '', cls: 'diff-pad' });
    for (const l of oldLines) html += `<tr class="${l.cls}"><td class="diff-num">${l.num}</td><td class="diff-code">${esc(l.text)}</td></tr>`;
    html += '</table></div><div class="diff-col diff-col-new"><div class="diff-col-label">New</div><table class="diff-table">';
    for (const l of newLines) html += `<tr class="${l.cls}"><td class="diff-num">${l.num}</td><td class="diff-code">${esc(l.text)}</td></tr>`;
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

// tree tab: visual SVG branch graph
const LANE_COLORS = ['#4a9eff', '#ff6b9d', '#50e3c2', '#f5a623', '#bd10e0', '#7ed321', '#d0021b', '#8b572a'];

async function renderTree(el) {
  let result;
  try {
    result = await rpc('poor-cli/executeCommand', {
      command: 'git log --all --format="%H|%P|%s|%D" -60'
    });
  } catch {
    el.innerHTML = '<p style="color:var(--text-muted)">Could not load git graph</p>';
    return;
  }
  const raw = (result.output || result.stdout || '').trim();
  if (!raw) { el.innerHTML = '<p style="color:var(--text-muted)">No commits</p>'; return; }

  const commits = [];
  for (const line of raw.split('\n')) {
    const [hash, parents, message, refs] = line.split('|');
    if (!hash) continue;
    commits.push({
      hash: hash.trim(),
      parents: (parents || '').trim().split(' ').filter(Boolean),
      message: (message || '').trim(),
      refs: (refs || '').trim(),
    });
  }
  if (!commits.length) { el.innerHTML = '<p style="color:var(--text-muted)">No commits</p>'; return; }

  // assign lanes: each active branch gets a column
  const lanes = []; // active commit hashes occupying each lane
  const commitLane = new Map(); // hash -> lane index
  const ROW_H = 40, LANE_W = 24, NODE_R = 5, PAD_LEFT = 16;

  const rows = [];
  for (const c of commits) {
    // find or assign lane for this commit
    let lane = lanes.indexOf(c.hash);
    if (lane === -1) {
      lane = lanes.indexOf(null);
      if (lane === -1) { lane = lanes.length; lanes.push(null); }
    }
    lanes[lane] = null; // free this lane
    commitLane.set(c.hash, lane);

    // assign parent lanes
    const parentLanes = [];
    for (let i = 0; i < c.parents.length; i++) {
      const p = c.parents[i];
      let pLane = lanes.indexOf(p);
      if (pLane === -1) {
        if (i === 0) { pLane = lane; } // first parent takes same lane
        else {
          pLane = lanes.indexOf(null);
          if (pLane === -1) { pLane = lanes.length; lanes.push(null); }
        }
      }
      lanes[pLane] = p;
      parentLanes.push(pLane);
    }
    rows.push({ commit: c, lane, parentLanes, activeLanes: [...lanes] });
  }

  const maxLanes = Math.max(...rows.map(r => Math.max(r.lane + 1, ...r.parentLanes.map(l => l + 1))), 1);
  const svgW = PAD_LEFT + maxLanes * LANE_W + 20;
  const svgH = rows.length * ROW_H + 20;
  const textX = svgW + 8;

  let svg = `<div class="git-graph-container"><svg class="git-graph-svg" width="${svgW}" height="${svgH}">`;

  // draw edges first (behind nodes)
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const y = i * ROW_H + ROW_H / 2;
    const x = PAD_LEFT + r.lane * LANE_W + LANE_W / 2;
    for (let pi = 0; pi < r.parentLanes.length; pi++) {
      const pLane = r.parentLanes[pi];
      // find parent row index
      const pIdx = rows.findIndex((pr, idx) => idx > i && pr.commit.hash === r.commit.parents[pi]);
      if (pIdx === -1) continue;
      const py = pIdx * ROW_H + ROW_H / 2;
      const px = PAD_LEFT + pLane * LANE_W + LANE_W / 2;
      const color = LANE_COLORS[pLane % LANE_COLORS.length];
      if (x === px) {
        svg += `<line x1="${x}" y1="${y}" x2="${px}" y2="${py}" stroke="${color}" stroke-width="2"/>`;
      } else {
        const midY = y + ROW_H * 0.6;
        svg += `<path d="M${x},${y} C${x},${midY} ${px},${midY} ${px},${py}" fill="none" stroke="${color}" stroke-width="2"/>`;
      }
    }
  }

  // draw nodes
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const y = i * ROW_H + ROW_H / 2;
    const x = PAD_LEFT + r.lane * LANE_W + LANE_W / 2;
    const color = LANE_COLORS[r.lane % LANE_COLORS.length];
    const isHead = r.commit.refs.includes('HEAD');
    svg += `<circle cx="${x}" cy="${y}" r="${isHead ? NODE_R + 2 : NODE_R}" fill="${color}" stroke="${isHead ? '#fff' : 'none'}" stroke-width="${isHead ? 2 : 0}"/>`;
  }
  svg += '</svg>';

  // commit labels (right of SVG)
  svg += '<div class="git-graph-labels" style="padding-top:0">';
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const color = LANE_COLORS[r.lane % LANE_COLORS.length];
    const shortHash = r.commit.hash.substring(0, 7);
    let refBadges = '';
    if (r.commit.refs) {
      const refs = r.commit.refs.split(',').map(s => s.trim()).filter(Boolean);
      for (const ref of refs) {
        const isHead = ref.includes('HEAD');
        refBadges += `<span class="git-graph-ref${isHead ? ' git-graph-head' : ''}" style="background:${color}">${esc(ref)}</span> `;
      }
    }
    svg += `<div class="git-graph-row" style="height:${ROW_H}px">`;
    svg += `<span class="git-graph-hash" style="color:${color}">${shortHash}</span> `;
    svg += refBadges;
    svg += `<span class="git-graph-msg">${esc(r.commit.message)}</span>`;
    svg += '</div>';
  }
  svg += '</div></div>';
  el.innerHTML = svg;
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
