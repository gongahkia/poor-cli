// context view
import { rpc } from './rpc.js';

export async function initContext() {
  const content = document.getElementById('context-content');
  content.innerHTML = '<p>Loading context...</p>';
  try {
    const status = await rpc('get_status_view', {});
    let html = '';
    const files = status?.contextFiles || status?.context?.files || [];
    if (files.length) {
      html += '<h3>Context Files</h3>';
      files.forEach(f => {
        html += `<div class="item-card"><code>${esc(typeof f === 'string' ? f : f.path || f.name || '?')}</code></div>`;
      });
    } else {
      html += '<p style="color:var(--text-muted)">No context files attached</p>';
    }
    html += '<p style="margin-top:12px;color:var(--text-muted);font-size:12px">Use <code>@filename</code> in chat to add files to context.</p>';
    content.innerHTML = html;
  } catch (e) {
    console.warn('[context] initContext:', e);
    content.innerHTML = '<p style="color:var(--text-muted)">Context unavailable — backend not connected</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
