// timeline view — agent run history with diffs
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initTimeline() {
  const container = document.getElementById('timeline-content');
  if (!container) return;
  await refreshTimeline();
}

export async function refreshTimeline() {
  const container = document.getElementById('timeline-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
  try {
    const result = await rpc('poor-cli/listRuns', {});
    const runs = result.runs || result || [];
    container.innerHTML = '';
    if (!runs.length) { container.innerHTML = '<p style="color:var(--text-muted)">No runs in timeline</p>'; return; }
    runs.forEach((run, i) => {
      const entry = document.createElement('div');
      entry.className = 'item-card timeline-entry';
      const statusCls = run.status === 'success' ? 'badge-success' : run.status === 'failed' ? 'badge-error' : 'badge';
      entry.innerHTML = `<div class="timeline-header">`
        + `<span class="timeline-dot"></span>`
        + `<h3>${esc(run.title || run.id || `Run #${i + 1}`)}</h3>`
        + `<span class="${statusCls}">${esc(run.status || 'unknown')}</span>`
        + `<span style="color:var(--text-muted);font-size:12px;margin-left:auto">${esc(run.timestamp || run.createdAt || '')}</span>`
        + `</div>`
        + `<p>${esc(run.summary || run.prompt || '')}</p>`
        + `<div class="timeline-diff" hidden></div>`
        + `<button class="btn btn-sm timeline-expand-btn">Show diff</button>`;
      const diffPanel = entry.querySelector('.timeline-diff');
      const expandBtn = entry.querySelector('.timeline-expand-btn');
      expandBtn.onclick = async () => {
        if (!diffPanel.hidden) { diffPanel.hidden = true; expandBtn.textContent = 'Show diff'; return; }
        diffPanel.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
        diffPanel.hidden = false;
        expandBtn.textContent = 'Hide diff';
        try {
          const wf = await rpc('poor-cli/getWorkflow', { runId: run.id || run.runId });
          const diff = wf.diff || wf.changes || JSON.stringify(wf, null, 2);
          diffPanel.innerHTML = `<pre>${esc(typeof diff === 'string' ? diff : JSON.stringify(diff, null, 2))}</pre>`;
        } catch (e) { diffPanel.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`; }
      };
      container.appendChild(entry);
    });
  } catch (_) {
    container.innerHTML = '<p style="color:var(--text-muted)">Timeline unavailable — backend not connected</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
