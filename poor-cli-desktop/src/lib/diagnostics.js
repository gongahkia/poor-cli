// diagnostics view
import { rpc } from './rpc.js';

export async function initDiagnostics() {
  const content = document.getElementById('diagnostics-content');
  content.innerHTML = '<p>Loading diagnostics...</p>';
  try {
    const [doctor, policy, trust, sandbox] = await Promise.all([
      rpc('get_doctor_report', {}).catch(() => null),
      rpc('get_policy_status', {}).catch(() => null),
      rpc('get_trust_view', {}).catch(() => null),
      rpc('get_sandbox_status', {}).catch(() => null),
    ]);
    let html = '';
    // doctor
    html += '<h3>Doctor</h3>';
    if (doctor) {
      const checks = doctor.checks || doctor.results || [];
      if (Array.isArray(checks) && checks.length) {
        checks.forEach(c => {
          const icon = c.status === 'ok' || c.passed ? '&#10003;' : '&#10007;';
          const cls = c.status === 'ok' || c.passed ? 'pass' : 'fail';
          html += `<div class="diag-check ${cls}"><span>${icon}</span> ${esc(c.name || c.check || '?')}: ${esc(c.message || c.detail || '')}</div>`;
        });
      } else {
        html += `<pre>${esc(JSON.stringify(doctor, null, 2))}</pre>`;
      }
    } else {
      html += '<p style="color:var(--text-muted)">Doctor unavailable</p>';
    }
    // policy
    html += '<h3 style="margin-top:16px">Policy</h3>';
    html += policy ? `<pre>${esc(JSON.stringify(policy, null, 2))}</pre>` : '<p style="color:var(--text-muted)">Policy unavailable</p>';
    // trust
    html += '<h3 style="margin-top:16px">Trust</h3>';
    html += trust ? `<pre>${esc(JSON.stringify(trust, null, 2))}</pre>` : '<p style="color:var(--text-muted)">Trust unavailable</p>';
    // sandbox
    html += '<h3 style="margin-top:16px">Sandbox</h3>';
    html += sandbox ? `<pre>${esc(JSON.stringify(sandbox, null, 2))}</pre>` : '<p style="color:var(--text-muted)">Sandbox unavailable</p>';
    content.innerHTML = html;
  } catch (_) {
    content.innerHTML = '<p style="color:var(--text-muted)">Diagnostics unavailable — backend not connected</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
