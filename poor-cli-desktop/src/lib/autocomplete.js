// autocomplete — slash commands (/) and @ mentions popup
import { rpc } from './rpc.js';

const popup = document.getElementById('autocomplete-popup');
const input = document.getElementById('chat-input');

// full command set — synced from command_manifest.json (80 non-hidden commands)
const COMMANDS = [
  { cmd: '/help', desc: 'Show all available commands', cat: 'Core Workflow' },
  { cmd: '/plan', desc: 'Generate a plan before executing', cat: 'Core Workflow' },
  { cmd: '/history', desc: 'Show recent messages', cat: 'Core Workflow' },
  { cmd: '/sessions', desc: 'List recent sessions', cat: 'Core Workflow' },
  { cmd: '/new-session', desc: 'Start a fresh session', cat: 'Core Workflow' },
  { cmd: '/queue', desc: 'Manage prompt queue (add/list/clear/drop)', cat: 'Core Workflow' },
  { cmd: '/compact', desc: 'Manage context (compact/compress/handoff)', cat: 'Core Workflow' },
  { cmd: '/search', desc: 'Search transcript, tools, and diffs', cat: 'Core Workflow' },
  { cmd: '/status', desc: 'Show canonical session status summary', cat: 'Core Workflow' },
  { cmd: '/runs', desc: 'Inspect recent shared run history', cat: 'Core Workflow' },
  { cmd: '/workflow', desc: 'Inspect guided workflow templates', cat: 'Core Workflow' },
  { cmd: '/export', desc: 'Export conversation history', cat: 'Core Workflow' },
  { cmd: '/retry', desc: 'Retry last request', cat: 'Core Workflow' },
  { cmd: '/quit', desc: 'Exit the TUI', cat: 'Core Workflow' },
  { cmd: '/clear', desc: 'Clear conversation history', cat: 'Core Workflow' },
  { cmd: '/cost', desc: 'Show session token usage and estimated cost', cat: 'Core Workflow' },
  { cmd: '/ollama-models', desc: 'List locally available Ollama models', cat: 'Core Workflow' },
  { cmd: '/mcp-health', desc: 'Check health of MCP servers', cat: 'Core Workflow' },
  { cmd: '/review', desc: 'Review code or staged diff', cat: 'Review & Safety' },
  { cmd: '/test', desc: 'Generate tests for a file', cat: 'Review & Safety' },
  { cmd: '/permission-mode', desc: 'Show permission mode', cat: 'Review & Safety' },
  { cmd: '/sandbox', desc: 'Show or set sandbox preset', cat: 'Review & Safety' },
  { cmd: '/instructions', desc: 'Inspect the active instruction stack', cat: 'Review & Safety' },
  { cmd: '/memory', desc: 'Show or update repo-local memory', cat: 'Review & Safety' },
  { cmd: '/policy', desc: 'Inspect repo-local hooks and audit status', cat: 'Review & Safety' },
  { cmd: '/context', desc: 'Open backend context inspector', cat: 'Review & Safety' },
  { cmd: '/trust', desc: 'Open the trust center', cat: 'Review & Safety' },
  { cmd: '/timeline', desc: 'Open agent timeline and diffs', cat: 'Review & Safety' },
  { cmd: '/fix-failures', desc: 'Analyze latest test/lint failure output', cat: 'Review & Safety' },
  { cmd: '/checkpoints', desc: 'Browse and manage checkpoints', cat: 'Review & Safety' },
  { cmd: '/checkpoint', desc: 'Create named checkpoint', cat: 'Review & Safety' },
  { cmd: '/diff', desc: 'Compare two files', cat: 'Review & Safety' },
  { cmd: '/undo', desc: 'Undo file changes (restore checkpoint)', cat: 'Review & Safety' },
  { cmd: '/plan-mode', desc: 'Toggle plan-first execution guidance', cat: 'Review & Safety' },
  { cmd: '/gc', desc: 'Clean up stale checkpoints', cat: 'Review & Safety' },
  { cmd: '/provider', desc: 'Show provider info, models, or switch (F2)', cat: 'Providers & Config' },
  { cmd: '/config', desc: 'Show active configuration', cat: 'Providers & Config' },
  { cmd: '/profile', desc: 'Set execution profile (speed|safe|deep-review)', cat: 'Providers & Config' },
  { cmd: '/settings', desc: 'List editable config settings', cat: 'Providers & Config' },
  { cmd: '/setup', desc: 'Open the guided setup summary', cat: 'Providers & Config' },
  { cmd: '/api-key', desc: 'Open the API key editor', cat: 'Providers & Config' },
  { cmd: '/theme', desc: 'Show or set UI theme', cat: 'Providers & Config' },
  { cmd: '/tools', desc: 'List backend tools', cat: 'Providers & Config' },
  { cmd: '/mcp', desc: 'Inspect or control MCP servers', cat: 'Providers & Config' },
  { cmd: '/doctor', desc: 'Open diagnostics with remediation', cat: 'Services & Shell' },
  { cmd: '/files', desc: 'List pinned context files', cat: 'Context & Reuse' },
  { cmd: '/add', desc: 'Pin file/directory for context', cat: 'Context & Reuse' },
  { cmd: '/drop', desc: 'Unpin context file', cat: 'Context & Reuse' },
  { cmd: '/clear-files', desc: 'Clear all pinned context files', cat: 'Context & Reuse' },
  { cmd: '/focus', desc: 'Manage persistent coding focus state', cat: 'Context & Reuse' },
  { cmd: '/resume', desc: 'Resume with branch/checkpoint/session summary', cat: 'Context & Reuse' },
  { cmd: '/workspace-map', desc: 'Summarize repository layout and hotspots', cat: 'Context & Reuse' },
  { cmd: '/bootstrap', desc: 'Detect project type and suggest quickstart', cat: 'Context & Reuse' },
  { cmd: '/context-budget', desc: 'Rank context files against a token budget', cat: 'Context & Reuse' },
  { cmd: '/image', desc: 'Queue image for next message', cat: 'Context & Reuse' },
  { cmd: '/save-prompt', desc: 'Save reusable prompt', cat: 'Context & Reuse' },
  { cmd: '/use', desc: 'Load and run saved prompt', cat: 'Context & Reuse' },
  { cmd: '/prompts', desc: 'List saved prompts', cat: 'Context & Reuse' },
  { cmd: '/save-session', desc: 'Save current session for later restore', cat: 'Context & Reuse' },
  { cmd: '/restore-session', desc: 'Restore most recent saved session', cat: 'Context & Reuse' },
  { cmd: '/autopilot', desc: 'Toggle bounded autonomous execution', cat: 'Automation & Tasks' },
  { cmd: '/qa', desc: 'Run background QA watch for lint/tests', cat: 'Automation & Tasks' },
  { cmd: '/task', desc: 'Manage durable background tasks', cat: 'Automation & Tasks' },
  { cmd: '/automation', desc: 'Inspect automation run history', cat: 'Automation & Tasks' },
  { cmd: '/inbox', desc: 'Show pending and actionable tasks', cat: 'Automation & Tasks' },
  { cmd: '/skills', desc: 'Inspect or run repo and user skills', cat: 'Automation & Tasks' },
  { cmd: '/commands', desc: 'Inspect or run repo and user commands', cat: 'Automation & Tasks' },
  { cmd: '/watch', desc: 'Watch directory for changes', cat: 'Automation & Tasks' },
  { cmd: '/unwatch', desc: 'Stop watch mode', cat: 'Automation & Tasks' },
  { cmd: '/service', desc: 'Manage local background services', cat: 'Services & Shell' },
  { cmd: '/ollama', desc: 'Manage Ollama service and models', cat: 'Services & Shell' },
  { cmd: '/run', desc: 'Run shell command via backend', cat: 'Services & Shell' },
  { cmd: '/read', desc: 'Read file through backend', cat: 'Services & Shell' },
  { cmd: '/commit', desc: 'Create commit message from staged diff', cat: 'Git & Workspace' },
  { cmd: '/collab', desc: 'Start, join, or manage collaboration', cat: 'Collaboration' },
  { cmd: '/pass', desc: 'Hand driver role to next collaborator', cat: 'Collaboration' },
  { cmd: '/suggest', desc: 'Send suggestion to active driver', cat: 'Collaboration' },
  { cmd: '/leave', desc: 'Disconnect from collaboration session', cat: 'Collaboration' },
  { cmd: '/economy', desc: 'Show or switch economy preset', cat: 'Economy & Output' },
  { cmd: '/savings', desc: 'Show economy savings dashboard', cat: 'Economy & Output' },
];

let activeIdx = 0;
let items = [];
let mode = null; // 'slash' | 'at' | null
let atQuery = '';
let fileDebounce = null;
let cachedSkills = null;

export function initAutocomplete() {
  input.addEventListener('input', onInput);
  input.addEventListener('keydown', onKeydown);
  document.addEventListener('click', (e) => {
    if (!popup.contains(e.target) && e.target !== input) close();
  });
}

function onInput() {
  const val = input.value;
  const pos = input.selectionStart;
  // detect / at start of line
  const lineStart = val.lastIndexOf('\n', pos - 1) + 1;
  const lineText = val.substring(lineStart, pos);
  if (lineText.startsWith('/')) {
    mode = 'slash';
    const filter = lineText.substring(1).toLowerCase();
    showSlash(filter);
    return;
  }
  // detect @ trigger
  const atPos = val.lastIndexOf('@', pos - 1);
  if (atPos >= 0 && atPos >= lineStart) {
    const beforeAt = atPos === 0 ? ' ' : val[atPos - 1];
    if (beforeAt === ' ' || beforeAt === '\n' || atPos === lineStart) {
      mode = 'at';
      atQuery = val.substring(atPos + 1, pos).toLowerCase();
      showAt(atQuery);
      return;
    }
  }
  close();
}

function onKeydown(e) {
  if (!mode) return;
  if (e.key === 'Escape') { e.preventDefault(); close(); return; }
  if (e.key === 'ArrowDown') { e.preventDefault(); navigate(1); return; }
  if (e.key === 'ArrowUp') { e.preventDefault(); navigate(-1); return; }
  if (e.key === 'Tab' || e.key === 'Enter') {
    if (items.length > 0 && !popup.hidden) {
      e.preventDefault();
      e.stopPropagation();
      selectItem(activeIdx);
      return;
    }
    // popup open but no items yet — block send so bare @ doesn't get submitted
    if (!popup.hidden) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
  }
}

function showSlash(filter) {
  const filtered = COMMANDS.filter(c =>
    c.cmd.toLowerCase().includes(filter) || c.desc.toLowerCase().includes(filter)
  );
  if (!filtered.length) { close(); return; }
  items = filtered;
  activeIdx = 0;
  renderSlash(filtered);
  popup.hidden = false;
}

function renderSlash(cmds) {
  const groups = {};
  for (const c of cmds) {
    if (!groups[c.cat]) groups[c.cat] = [];
    groups[c.cat].push(c);
  }
  let html = '';
  for (const [cat, list] of Object.entries(groups)) {
    html += `<div class="ac-group-label">${esc(cat)}</div>`;
    for (const c of list) {
      const idx = items.indexOf(c);
      html += `<div class="ac-item${idx === activeIdx ? ' active' : ''}" data-idx="${idx}"><span class="ac-item-icon">/</span><span class="ac-item-name">${esc(c.cmd.slice(1))}</span><span class="ac-item-desc">${esc(c.desc)}</span></div>`;
    }
  }
  popup.innerHTML = html;
  bindClicks();
}

async function showAt(query) {
  let skills = cachedSkills;
  if (!skills) {
    try {
      const result = await rpc('list_skills', {});
      skills = (result.skills || []).map(s => ({ name: s.name || s.skillFile, desc: s.description || '', scope: s.scope || '' }));
      cachedSkills = skills;
    } catch (e) { console.warn('[autocomplete] list_skills:', e); skills = []; }
  }
  const filteredSkills = skills.filter(s =>
    s.name.toLowerCase().includes(query) || s.desc.toLowerCase().includes(query)
  );
  // debounced file search
  if (fileDebounce) clearTimeout(fileDebounce);
  fileDebounce = setTimeout(() => searchFiles(query, filteredSkills), 200);
  // show skills immediately
  renderAt(filteredSkills, [], query);
  popup.hidden = false;
}

async function searchFiles(query, skills) {
  try {
    const result = await rpc('search_workspace_files', { query, limit: 15 });
    const files = result.files || [];
    renderAt(skills, files, query);
  } catch (e) { console.warn('[autocomplete] searchFiles:', e); }
}

function renderAt(skills, files, query) {
  items = [];
  let html = '';
  if (skills.length) {
    html += `<div class="ac-group-label">Skills</div>`;
    for (const s of skills) {
      const idx = items.length;
      items.push({ type: 'skill', value: s.name });
      html += `<div class="ac-item${idx === activeIdx ? ' active' : ''}" data-idx="${idx}"><span class="ac-item-icon">\u2699</span><span class="ac-item-name">${esc(s.name)}</span><span class="ac-item-desc">${esc(s.desc)}</span>${s.scope ? `<span class="ac-item-badge">${esc(s.scope)}</span>` : ''}</div>`;
    }
  }
  html += `<div class="ac-group-label">Files</div>`;
  if (files.length) {
    for (const f of files) {
      const idx = items.length;
      items.push({ type: 'file', value: f });
      const name = f.split('/').pop();
      const dir = f.includes('/') ? f.substring(0, f.lastIndexOf('/')) : '';
      html += `<div class="ac-item${idx === activeIdx ? ' active' : ''}" data-idx="${idx}"><span class="ac-item-icon">\u2759</span><span class="ac-item-name">${esc(name)}</span><span class="ac-item-desc">${esc(dir)}</span></div>`;
    }
  } else {
    html += `<div class="ac-hint">Type to search for files</div>`;
  }
  popup.innerHTML = html;
  if (activeIdx >= items.length) activeIdx = 0;
  bindClicks();
}

function navigate(dir) {
  if (!items.length) return;
  activeIdx = (activeIdx + dir + items.length) % items.length;
  popup.querySelectorAll('.ac-item').forEach((el, i) => {
    el.classList.toggle('active', parseInt(el.dataset.idx) === activeIdx);
  });
  const active = popup.querySelector('.ac-item.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}

function selectItem(idx) {
  if (mode === 'slash') {
    const cmd = items[idx];
    if (!cmd) return;
    const val = input.value;
    const pos = input.selectionStart;
    const lineStart = val.lastIndexOf('\n', pos - 1) + 1;
    input.value = val.substring(0, lineStart) + cmd.cmd + ' ' + val.substring(pos);
    input.selectionStart = input.selectionEnd = lineStart + cmd.cmd.length + 1;
  } else if (mode === 'at') {
    const item = items[idx];
    if (!item) return;
    const val = input.value;
    const pos = input.selectionStart;
    const atPos = val.lastIndexOf('@', pos - 1);
    const replacement = item.value.includes(' ') ? `@"${item.value}" ` : `@${item.value} `;
    input.value = val.substring(0, atPos) + replacement + val.substring(pos);
    input.selectionStart = input.selectionEnd = atPos + replacement.length;
  }
  input.focus();
  close();
}

function bindClicks() {
  popup.querySelectorAll('.ac-item').forEach(el => {
    el.addEventListener('mousedown', (e) => {
      e.preventDefault();
      selectItem(parseInt(el.dataset.idx));
    });
  });
}

function close() {
  popup.hidden = true;
  mode = null;
  items = [];
  activeIdx = 0;
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
