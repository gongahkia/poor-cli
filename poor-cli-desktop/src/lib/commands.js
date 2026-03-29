// custom commands view
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

export async function initCommands() {
  const list = document.getElementById('commands-list');
  list.innerHTML = '';
  try {
    const result = await rpc('list_custom_commands', {});
    const cmds = result.commands || result || [];
    if (!cmds.length) { list.innerHTML = '<p style="color:var(--text-muted)">No custom commands found</p>'; return; }
    cmds.forEach(c => {
      const card = document.createElement('div');
      card.className = 'item-card';
      card.innerHTML = `<div class="cmd-card-header"><h3>${esc(c.name || 'Untitled')}</h3>${c.source ? `<span class="badge">${esc(c.source)}</span>` : ''}</div>`
        + `<p>${esc(c.description || c.prompt || '')}</p>`
        + `<div class="cmd-actions"><button class="btn btn-sm btn-primary cmd-run-btn">Run</button></div>`;
      card.querySelector('.cmd-run-btn').onclick = () => runCommand(c.name);
      list.appendChild(card);
    });
  } catch (e) {
    console.warn('[commands] initCommands:', e);
    list.innerHTML = '<p style="color:var(--text-muted)">Commands unavailable — backend not connected</p>';
  }
}

async function runCommand(name) {
  const args = prompt(`Arguments for "${name}" (optional):`);
  if (args === null) return;
  try {
    await rpc('run_custom_command', { name, args: args || undefined });
    addMessage(`Command "${name}" executed.`, 'assistant');
  } catch (e) { addMessage(`Command failed: ${e}`, 'assistant'); }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
