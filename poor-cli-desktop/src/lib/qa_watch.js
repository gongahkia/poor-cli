// qa watcher — background lint and test results
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

let _qaTimer = null;

export async function initQaWatch() {
  const container = document.getElementById('qa-watch-content');
  if (!container) return;
  container.innerHTML = '';
  const controls = document.createElement('div');
  controls.className = 'view-toolbar';
  controls.innerHTML = `<button class="btn btn-sm btn-primary" id="qa-run-lint">Run Lint</button>`
    + `<button class="btn btn-sm btn-primary" id="qa-run-tests">Run Tests</button>`
    + `<button class="btn btn-sm" id="qa-refresh">Refresh</button>`;
  container.appendChild(controls);
  const split = document.createElement('div');
  split.className = 'qa-split';
  const left = document.createElement('div');
  left.id = 'qa-watch-left';
  left.className = 'qa-pane';
  const right = document.createElement('div');
  right.id = 'qa-watch-right';
  right.className = 'qa-pane';
  split.appendChild(left);
  split.appendChild(right);
  container.appendChild(split);
  document.getElementById('qa-run-lint').onclick = () => runQa('lint');
  document.getElementById('qa-run-tests').onclick = () => runQa('test');
  document.getElementById('qa-refresh').onclick = () => refreshQaWatch();
  await refreshQaWatch();
  if (_qaTimer) clearInterval(_qaTimer);
  _qaTimer = setInterval(() => {
    if (container.offsetParent !== null) refreshQaWatch();
  }, 15000);
}

export async function refreshQaWatch() {
  const left = document.getElementById('qa-watch-left');
  const right = document.getElementById('qa-watch-right');
  if (!left || !right) return;
  left.innerHTML = '<h3>File Watcher</h3>';
  right.innerHTML = '<h3>Results</h3>';
  try {
    const status = await rpc('get_status_view', {});
    const changes = status.fileChanges || status.changes || {};
    if (changes.filesChanged) {
      left.innerHTML += `<div class="item-card"><p><strong>${changes.filesChanged}</strong> file(s) changed</p>`
        + `<p class="item-card-meta"><span class="qa-add">+${changes.additions || 0}</span> / <span class="qa-del">-${changes.deletions || 0}</span></p></div>`;
    } else {
      left.innerHTML += '<p class="view-empty-text">No file changes detected</p>';
    }
    const mutations = status.lastMutations || status.mutations || [];
    if (mutations.length) {
      mutations.slice(0, 20).forEach(m => {
        const el = document.createElement('div');
        el.className = 'qa-file-item';
        el.innerHTML = `<span>${esc(m.file || m.path || m)}</span>`;
        left.appendChild(el);
      });
    }
  } catch (e) {
    console.warn('[qa_watch] get_status_view:', e);
    left.innerHTML += '<p class="view-empty-text">Watcher unavailable</p>';
  }
  right.innerHTML += '<p class="view-empty-text">Run lint or tests to see results</p>';
}

async function runQa(type) {
  const right = document.getElementById('qa-watch-right');
  if (!right) return;
  right.innerHTML = `<h3>Results</h3><p class="view-empty-text">Running ${type}...</p>`;
  try {
    const result = await rpc('send_chat', { message: `/${type}` });
    const content = result.content || result.text || JSON.stringify(result, null, 2);
    right.innerHTML = '<h3>Results</h3>';
    const lines = content.split('\n');
    lines.forEach(line => {
      const el = document.createElement('div');
      el.className = 'qa-result-line';
      const pass = /pass|ok|success|\u2713/i.test(line);
      const fail = /fail|error|warn|\u2717/i.test(line);
      if (pass) el.innerHTML = `<span class="badge badge-ok">PASS</span> ${esc(line)}`;
      else if (fail) el.innerHTML = `<span class="badge badge-fail">FAIL</span> ${esc(line)}`;
      else el.textContent = line;
      right.appendChild(el);
    });
  } catch (e) {
    right.innerHTML = `<h3>Results</h3><p style="color:var(--error)">${esc(String(e))}</p>`;
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
