// skills & automations list views
import { rpc } from './rpc.js';

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
      card.innerHTML = `<h3>${esc(s.name || 'Untitled')}</h3><p>${esc(s.description || '')}</p>${s.source ? `<span class="badge">${esc(s.source)}</span>` : ''}`;
      list.appendChild(card);
    });
  } catch (_) {
    list.innerHTML = '<p style="color:var(--text-muted)">No skills available — backend not connected</p>';
  }
}

export async function initAutomations() {
  const list = document.getElementById('automations-list');
  list.innerHTML = '';
  try {
    const result = await rpc('list_automations', {});
    const autos = result.automations || result || [];
    if (!autos.length) { list.innerHTML = '<p style="color:var(--text-muted)">No automations found</p>'; return; }
    autos.forEach(a => {
      const card = document.createElement('div');
      card.className = 'item-card';
      card.innerHTML = `<h3>${esc(a.name || a.id || 'Untitled')}</h3><p>${esc(a.schedule || a.description || '')}</p><span class="badge">${a.enabled ? 'enabled' : 'disabled'}</span>`;
      list.appendChild(card);
    });
  } catch (_) {
    list.innerHTML = '<p style="color:var(--text-muted)">No automations available — backend not connected</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
