// diagnostics view
import { rpc } from './rpc.js';

export async function initDiagnostics() {
  const content = document.getElementById('diagnostics-content');
  content.innerHTML = '<p>Loading diagnostics...</p>';
  try {
    const [doctor, policy, trust, sandbox] = await Promise.all([
      rpc('get_doctor_report', {}).catch(e => { console.warn('[diagnostics] get_doctor_report:', e); return null; }),
      rpc('get_policy_status', {}).catch(e => { console.warn('[diagnostics] get_policy_status:', e); return null; }),
      rpc('get_trust_view', {}).catch(e => { console.warn('[diagnostics] get_trust_view:', e); return null; }),
      rpc('get_sandbox_status', {}).catch(e => { console.warn('[diagnostics] get_sandbox_status:', e); return null; }),
    ]);
    let html = '';
    html += renderDoctor(doctor);
    html += renderJsonSection('Policy', policy);
    html += renderJsonSection('Sandbox', sandbox);
    html += renderJsonSection('Trust', trust);
    content.innerHTML = html;
    content.querySelectorAll('.diag-section-header').forEach(h => {
      h.addEventListener('click', () => h.parentElement.classList.toggle('collapsed'));
    });
    content.querySelectorAll('.diag-copy-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const json = btn.closest('.diag-section').querySelector('.diag-json-raw').textContent;
        navigator.clipboard.writeText(json).then(() => {
          btn.textContent = 'Copied';
          setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
        });
      });
    });
  } catch (e) {
    console.warn('[diagnostics] initDiagnostics:', e);
    content.innerHTML = '<p style="color:var(--text-muted)">Diagnostics unavailable — backend not connected</p>';
  }
}

function renderDoctor(doctor) {
  let body = '';
  if (doctor) {
    const checks = doctor.checks || doctor.results || [];
    if (Array.isArray(checks) && checks.length) {
      checks.forEach(c => {
        const ok = c.status === 'ok' || c.passed;
        const cls = ok ? 'diag-pass' : 'diag-fail';
        const icon = ok ? '&#10003;' : '&#10007;';
        const name = esc(c.name || c.check || '?');
        const msg = esc(c.message || c.detail || '');
        body += `<div class="diag-check ${cls}"><span class="diag-icon">${icon}</span><span class="diag-label">${name}</span><span class="diag-msg">${msg}</span></div>`;
      });
    } else {
      body = `<pre class="diag-json">${highlightJson(doctor)}</pre>`;
    }
  } else {
    body = '<p style="color:var(--text-muted)">Doctor unavailable</p>';
  }
  return `<div class="diag-section"><div class="diag-section-header"><h3>Doctor</h3><span class="diag-toggle">&#9660;</span></div><div class="diag-section-body">${body}</div></div>`;
}

function renderJsonSection(title, data) {
  let body;
  if (data) {
    const raw = JSON.stringify(data, null, 2);
    body = `<div style="position:relative"><button class="diag-copy-btn">Copy</button><pre class="diag-json">${highlightJson(data)}</pre><pre class="diag-json-raw" hidden>${esc(raw)}</pre></div>`;
  } else {
    body = `<p style="color:var(--text-muted)">${esc(title)} unavailable</p>`;
  }
  return `<div class="diag-section"><div class="diag-section-header"><h3>${esc(title)}</h3><span class="diag-toggle">&#9660;</span></div><div class="diag-section-body">${body}</div></div>`;
}

function highlightJson(obj) {
  const raw = JSON.stringify(obj, null, 2);
  return raw.replace(/("(?:\\.|[^"\\])*")\s*:/g, '<span class="json-key">$1</span>:') // keys
    .replace(/:\s*("(?:\\.|[^"\\])*")/g, ': <span class="json-str">$1</span>') // string vals
    .replace(/:\s*(true|false)/g, ': <span class="json-bool">$1</span>') // bools
    .replace(/:\s*(\d+(?:\.\d+)?)/g, ': <span class="json-num">$1</span>') // numbers
    .replace(/:\s*(null)/g, ': <span class="json-null">$1</span>'); // null
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
