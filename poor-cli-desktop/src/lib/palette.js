// command palette — Cmd/Ctrl+P
import { rpc } from './rpc.js';
import { showView } from './views.js';
import { openProjectDialog } from './project_opener.js';

const COMMANDS = [
  // navigation
  { label: 'Open project', key: 'Ctrl+O', action: () => openProjectDialog(), cat: 'Navigate' },
  { label: 'New thread', key: 'Ctrl+N', action: () => rpc('create_session', { label: `session-${Date.now()}` }), cat: 'Navigate' },
  { label: 'Chat', key: '/chat', action: () => showView('chat'), cat: 'Navigate' },
  { label: 'Tasks', key: '/tasks', action: () => showView('tasks'), cat: 'Navigate' },
  { label: 'Skills', key: '/skills', action: () => showView('skills'), cat: 'Navigate' },
  { label: 'Commands', key: '/commands', action: () => showView('commands'), cat: 'Navigate' },
  { label: 'Automations', key: '/automations', action: () => showView('automations'), cat: 'Navigate' },
  { label: 'Workflows', key: '/workflows', action: () => showView('workflows'), cat: 'Navigate' },
  { label: 'Checkpoints', key: '/checkpoints', action: () => showView('checkpoints'), cat: 'Navigate' },
  { label: 'Tools', key: '/tools', action: () => showView('tools'), cat: 'Navigate' },
  { label: 'Git', key: '/git', action: () => showView('git'), cat: 'Navigate' },
  { label: 'Mission Control', key: '/mc', action: () => showView('mission-control'), cat: 'Navigate' },
  { label: 'Diagnostics', key: '/diagnostics', action: () => showView('diagnostics'), cat: 'Navigate' },
  { label: 'Settings', key: 'Ctrl+,', action: () => showView('settings'), cat: 'Navigate' },
  { label: 'Context', key: '/context', action: () => showView('context'), cat: 'Navigate' },
  { label: 'History', key: '/history', action: () => showView('history'), cat: 'Navigate' },
  // actions
  { label: 'Toggle sidebar', key: 'Ctrl+B', action: () => document.getElementById('sidebar')?.classList.toggle('collapsed'), cat: 'Actions' },
  { label: 'Toggle file changes', key: 'Ctrl+J', action: () => document.getElementById('file-changes-panel')?.classList.toggle('hidden'), cat: 'Actions' },
  { label: 'Collaborate', key: '/collab', action: () => document.getElementById('wb-collab')?.click(), cat: 'Actions' },
  { label: 'Export conversation', key: '/export', action: () => { const m = document.getElementById('export-modal'); if (m) m.hidden = false; }, cat: 'Actions' },
  { label: 'Compact context', key: '/compact', action: 'slash', cat: 'Actions' },
  { label: 'Clear history', key: '/clear', action: 'slash', cat: 'Actions' },
  // info
  { label: 'Help', key: '/help', action: 'slash', cat: 'Info' },
  { label: 'Status', key: '/status', action: 'slash', cat: 'Info' },
  { label: 'Cost', key: '/cost', action: 'slash', cat: 'Info' },
  { label: 'Provider info', key: '/provider', action: 'slash', cat: 'Info' },
  { label: 'API key status', key: '/api-key', action: 'slash', cat: 'Info' },
  { label: 'Config', key: '/config', action: 'slash', cat: 'Info' },
  { label: 'Doctor', key: '/doctor', action: 'slash', cat: 'Info' },
  { label: 'Sandbox', key: '/sandbox', action: 'slash', cat: 'Info' },
  // workflows
  { label: 'Review', key: '/review', action: 'slash', cat: 'Workflows' },
  { label: 'Test', key: '/test', action: 'slash', cat: 'Workflows' },
  { label: 'Debug', key: '/debug', action: 'slash', cat: 'Workflows' },
  { label: 'Implement', key: '/implement', action: 'slash', cat: 'Workflows' },
  { label: 'Summarize', key: '/summarize', action: 'slash', cat: 'Workflows' },
  { label: 'QA', key: '/qa', action: 'slash', cat: 'Workflows' },
  { label: 'Plan', key: '/plan', action: 'slash', cat: 'Workflows' },
  { label: 'Standup', key: '/standup', action: 'slash', cat: 'Workflows' },
  { label: 'Weekly update', key: '/weekly-update', action: 'slash', cat: 'Workflows' },
  { label: 'Release notes', key: '/release-notes', action: 'slash', cat: 'Workflows' },
  { label: 'Scan bugs', key: '/scan-bugs', action: 'slash', cat: 'Workflows' },
  { label: 'CI failures', key: '/ci-failures', action: 'slash', cat: 'Workflows' },
  { label: 'Triage', key: '/triage', action: 'slash', cat: 'Workflows' },
  // workflow pass-through
  { label: 'PR summary', key: '/pr-summary', action: 'slash', cat: 'Workflows' },
  { label: 'Changelog', key: '/changelog', action: 'slash', cat: 'Workflows' },
  { label: 'CI debug', key: '/ci-debug', action: 'slash', cat: 'Workflows' },
  { label: 'Test coverage', key: '/test-coverage', action: 'slash', cat: 'Workflows' },
  { label: 'Bootstrap', key: '/bootstrap', action: 'slash', cat: 'Workflows' },
  { label: 'Dep drift', key: '/dep-drift', action: 'slash', cat: 'Workflows' },
  { label: 'Dep upgrade', key: '/dep-upgrade', action: 'slash', cat: 'Workflows' },
  { label: 'Explain diff', key: '/explain-diff', action: 'slash', cat: 'Workflows' },
  { label: 'Perf audit', key: '/perf-audit', action: 'slash', cat: 'Workflows' },
  { label: 'Release check', key: '/release-check', action: 'slash', cat: 'Workflows' },
  { label: 'Update docs', key: '/update-docs', action: 'slash', cat: 'Workflows' },
  { label: 'Perf opportunity', key: '/perf-opportunity', action: 'slash', cat: 'Workflows' },
  { label: 'Skill suggest', key: '/skill-suggest', action: 'slash', cat: 'Workflows' },
  // views
  { label: 'Timeline', key: '/timeline', action: () => showView('timeline'), cat: 'Navigate' },
  { label: 'Memory', key: '/memory', action: () => showView('memory'), cat: 'Navigate' },
  { label: 'Sessions', key: '/sessions', action: () => showView('sessions'), cat: 'Navigate' },
  { label: 'Economy', key: '/economy-view', action: () => showView('economy'), cat: 'Navigate' },
  { label: 'Instructions', key: '/instructions', action: () => showView('instructions'), cat: 'Navigate' },
  { label: 'Prompt Library', key: '/prompt-library', action: () => showView('prompt-library'), cat: 'Navigate' },
  { label: 'QA Watch', key: '/qa-watch', action: () => showView('qa-watch'), cat: 'Navigate' },
  // git
  { label: 'Commit', key: '/commit', action: 'slash', cat: 'Git' },
  { label: 'Diff', key: '/diff', action: 'slash', cat: 'Git' },
  { label: 'Undo', key: '/undo', action: 'slash', cat: 'Git' },
  { label: 'Checkpoint', key: '/checkpoint', action: 'slash', cat: 'Git' },
];

let selected = 0;
let filtered = [];

export function initPalette() {
  const overlay = document.getElementById('command-palette');
  const input = document.getElementById('palette-input');
  const list = document.getElementById('palette-list');

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'p') {
      e.preventDefault();
      overlay.hidden = !overlay.hidden;
      if (!overlay.hidden) {
        input.value = '';
        selected = 0;
        render('');
        input.focus();
      }
    }
    if (e.key === 'Escape' && !overlay.hidden) {
      overlay.hidden = true;
    }
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.hidden = true;
  });

  input.addEventListener('input', () => {
    selected = 0;
    render(input.value);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); selected = Math.min(selected + 1, filtered.length - 1); highlight(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); selected = Math.max(selected - 1, 0); highlight(); }
    else if (e.key === 'Enter') { e.preventDefault(); execute(selected); }
  });

  function render(query) {
    const q = query.toLowerCase().trim();
    filtered = q ? COMMANDS.filter(c => c.label.toLowerCase().includes(q) || c.key.includes(q) || (c.cat || '').toLowerCase().includes(q)) : COMMANDS;
    list.innerHTML = '';
    let lastCat = '';
    filtered.forEach((cmd, i) => {
      if (cmd.cat && cmd.cat !== lastCat) {
        const catDiv = document.createElement('div');
        catDiv.className = 'palette-cat';
        catDiv.textContent = cmd.cat;
        list.appendChild(catDiv);
        lastCat = cmd.cat;
      }
      const div = document.createElement('div');
      div.className = `palette-item${i === selected ? ' active' : ''}`;
      div.innerHTML = `<span class="palette-label">${esc(cmd.label)}</span><span class="palette-key">${esc(cmd.key)}</span>`;
      div.addEventListener('click', () => execute(i));
      div.addEventListener('mouseenter', () => { selected = i; highlight(); });
      list.appendChild(div);
    });
  }

  function highlight() {
    list.querySelectorAll('.palette-item').forEach((el, i) => {
      el.classList.toggle('active', i === selected);
    });
    const active = list.querySelector('.palette-item.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
  }

  function execute(idx) {
    const cmd = filtered[idx];
    if (!cmd) return;
    overlay.hidden = true;
    if (cmd.action === 'slash') {
      const chatInput = document.getElementById('chat-input');
      chatInput.value = cmd.key;
      chatInput.focus();
      // trigger send via the send button click
      setTimeout(() => document.getElementById('send-btn').click(), 0);
    } else if (typeof cmd.action === 'function') {
      cmd.action();
    }
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
