// skills & automations views
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initSkills() {
  const list = document.getElementById('skills-list');
  list.innerHTML = '';
  try {
    const result = await rpc('list_skills', {});
    const skills = result.skills || result || [];
    if (!skills.length) { list.innerHTML = '<p style="color:var(--text-muted)">No skills found</p>'; return; }
    skills.forEach(s => {
      const card = document.createElement('div');
      card.className = 'item-card';
      card.innerHTML = `<div class="skill-card-header"><h3>${esc(s.name || 'Untitled')}</h3>${s.source ? `<span class="badge">${esc(s.source)}</span>` : ''}</div>`
        + `<p>${esc(s.description || '')}</p>`
        + `<div class="skill-actions"><button class="btn btn-sm btn-primary skill-run-btn">Run</button></div>`;
      card.querySelector('.skill-run-btn').onclick = () => runSkill(s.name);
      list.appendChild(card);
    });
  } catch (e) {
    console.warn('[skills] list_skills:', e);
    list.innerHTML = '<p style="color:var(--text-muted)">No skills available — backend not connected</p>';
  }
}

async function runSkill(name) {
  const args = prompt(`Arguments for skill "${name}" (optional):`);
  if (args === null) return;
  try {
    const msg = args ? `/skills run ${name} ${args}` : `/skills run ${name}`;
    await rpc('send_chat', { message: msg });
    addMessage(`Skill "${name}" executed.`, 'assistant');
  } catch (e) { addMessage(`Skill run failed: ${e}`, 'assistant'); }
}

export async function initAutomations() {
  const list = document.getElementById('automations-list');
  list.innerHTML = '';
  // create button
  const header = document.createElement('div');
  header.className = 'automations-header';
  header.innerHTML = '<button class="btn btn-primary btn-sm" id="create-auto-btn">+ New Automation</button>';
  list.parentElement.querySelector('h2').after(header);
  header.querySelector('#create-auto-btn').onclick = () => { document.getElementById('create-automation-modal').hidden = false; document.getElementById('auto-name-input').focus(); };
  document.getElementById('auto-modal-cancel').onclick = () => { document.getElementById('create-automation-modal').hidden = true; };
  document.getElementById('auto-modal-create').onclick = createAutomation;
  await refreshAutomations();
}

async function refreshAutomations() {
  const list = document.getElementById('automations-list');
  list.innerHTML = '';
  try {
    const result = await rpc('list_automations', {});
    const autos = result.automations || result || [];
    if (!autos.length) { list.innerHTML = '<p style="color:var(--text-muted)">No automations found</p>'; return; }
    autos.forEach(a => {
      const aid = a.automationId || a.id || a.name;
      const card = document.createElement('div');
      card.className = 'item-card automation-card';
      card.innerHTML = `<div class="auto-card-header"><h3>${esc(a.name || aid || 'Untitled')}</h3><span class="badge">${a.enabled ? 'enabled' : 'disabled'}</span></div>`
        + `<p>${esc(a.scheduleSummary || a.schedule || a.description || '')}</p>`
        + (a.lastRunStatus ? `<div class="auto-last-run">Last: <span class="badge">${esc(a.lastRunStatus)}</span>${a.lastRunAt ? ` ${relTime(a.lastRunAt)}` : ''}</div>` : '')
        + `<div class="auto-actions">`
        + `<label class="toggle-label"><input type="checkbox" class="auto-toggle" ${a.enabled ? 'checked' : ''} /> ${a.enabled ? 'On' : 'Off'}</label>`
        + `<button class="btn btn-sm btn-primary" data-act="run">Run Now</button>`
        + `<button class="btn btn-sm" data-act="history">History</button>`
        + `</div>`
        + `<div class="auto-history-panel" hidden></div>`;
      card.querySelector('.auto-toggle').onchange = (e) => toggleAutomation(aid, e.target.checked);
      card.querySelector('[data-act="run"]').onclick = () => runAutomationNow(aid);
      card.querySelector('[data-act="history"]').onclick = () => showAutomationHistory(aid, card.querySelector('.auto-history-panel'));
      list.appendChild(card);
    });
  } catch (e) {
    console.warn('[skills] list_automations:', e);
    list.innerHTML = '<p style="color:var(--text-muted)">No automations available — backend not connected</p>';
  }
}

async function toggleAutomation(id, enabled) {
  try {
    await rpc('set_automation_enabled', { automation_id: id, enabled });
  } catch (e) { addMessage(`Toggle failed: ${e}`, 'assistant'); }
  await refreshAutomations();
}

async function runAutomationNow(id) {
  try {
    addMessage(`Running automation ${id}...`, 'assistant');
    await rpc('run_automation_now', { automation_id: id });
    addMessage(`Automation ${id} completed.`, 'assistant');
    await refreshAutomations();
  } catch (e) { addMessage(`Run failed: ${e}`, 'assistant'); }
}

async function showAutomationHistory(id, panel) {
  if (!panel.hidden) { panel.hidden = true; return; }
  panel.hidden = false;
  panel.innerHTML = '<p>Loading...</p>';
  try {
    const result = await rpc('get_automation_history', { automation_id: id, limit: 10 });
    const runs = result.history || result.runs || result || [];
    if (!runs.length) { panel.innerHTML = '<p style="color:var(--text-muted)">No history</p>'; return; }
    panel.innerHTML = runs.map(r =>
      `<div class="auto-history-item"><span class="badge">${esc(r.status || '?')}</span> ${esc(r.summary || r.taskId || '')} <span class="auto-history-time">${r.finishedAt ? relTime(r.finishedAt) : ''}</span></div>`
    ).join('');
  } catch (e) {
    panel.innerHTML = `<p style="color:var(--error)">${esc(String(e))}</p>`;
  }
}

async function createAutomation() {
  const name = document.getElementById('auto-name-input').value.trim();
  const prompt_text = document.getElementById('auto-prompt-input').value.trim();
  if (!name || !prompt_text) return;
  const scheduleType = document.getElementById('auto-schedule-type').value;
  const interval = parseInt(document.getElementById('auto-interval-input').value) || 60;
  const approval = document.getElementById('auto-approval-check').checked;
  document.getElementById('create-automation-modal').hidden = true;
  try {
    await rpc('create_automation', { name, prompt: prompt_text, schedule_type: scheduleType, interval_minutes: interval, requires_approval: approval });
    await refreshAutomations();
  } catch (e) { addMessage(`Automation creation failed: ${e}`, 'assistant'); }
}

function relTime(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return 'now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
