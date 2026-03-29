// timeline view — agent run history with diffs
import { rpc } from './rpc.js';

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
    const result = await rpc('list_runs', {});
    const runs = result.runs || result || [];
    container.innerHTML = '';
    if (!runs.length) {
      container.innerHTML = '<div class="tl-empty"><span class="tl-empty-icon">&#9711;</span><p>No runs yet</p></div>';
      return;
    }
    const list = document.createElement('div');
    list.className = 'tl-list';
    runs.forEach((run, i) => {
      const ok = run.status === 'success';
      const fail = run.status === 'failed';
      const statusCls = ok ? 'tl-badge-ok' : fail ? 'tl-badge-fail' : 'tl-badge';
      const icon = ok ? '&#10003;' : fail ? '&#10007;' : '&#8226;';
      const entry = document.createElement('div');
      entry.className = 'tl-entry';
      entry.innerHTML = `<div class="tl-rail"><span class="tl-dot ${ok ? 'tl-dot-ok' : fail ? 'tl-dot-fail' : ''}">${icon}</span><span class="tl-line"></span></div>`
        + `<div class="tl-body">`
        + `<div class="tl-head"><h4>${esc(run.title || run.id || `Run #${i + 1}`)}</h4><span class="${statusCls}">${esc(run.status || 'unknown')}</span>`
        + `<span class="tl-time">${esc(run.timestamp || run.createdAt || '')}</span></div>`
        + `<p class="tl-summary">${esc(run.summary || run.prompt || '')}</p>`
        + `<div class="tl-diff" hidden></div>`
        + `<button class="btn btn-sm tl-expand-btn">Show diff</button>`
        + `</div>`;
      const diffPanel = entry.querySelector('.tl-diff');
      const expandBtn = entry.querySelector('.tl-expand-btn');
      expandBtn.onclick = async () => {
        if (!diffPanel.hidden) { diffPanel.hidden = true; expandBtn.textContent = 'Show diff'; return; }
        diffPanel.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
        diffPanel.hidden = false;
        expandBtn.textContent = 'Hide diff';
        try {
          const wf = await rpc('get_workflow', { name: run.id || run.runId });
          const diff = wf.diff || wf.changes || JSON.stringify(wf, null, 2);
          diffPanel.innerHTML = `<pre class="tl-diff-pre">${esc(typeof diff === 'string' ? diff : JSON.stringify(diff, null, 2))}</pre>`;
        } catch (e) { diffPanel.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`; }
      };
      list.appendChild(entry);
    });
    container.appendChild(list);
  } catch (e) {
    console.warn('[timeline] list_runs:', e);
    container.innerHTML = '<div class="tl-empty"><span class="tl-empty-icon">&#9888;</span><p>Timeline unavailable — backend not connected</p></div>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
