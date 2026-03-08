import { S, fn } from './state.js';
let overlayEl, inputEl, listEl;
let commands = [];
export function initCommandPalette() {
  fn.openCommandPalette = open;
  fn.closeCommandPalette = close;
  overlayEl = document.getElementById('cmd-palette');
  inputEl = document.getElementById('cmd-input');
  listEl = document.getElementById('cmd-list');
  inputEl.addEventListener('input', () => render(inputEl.value));
  inputEl.addEventListener('keydown', onKey);
  overlayEl.addEventListener('mousedown', (e) => { if (e.target === overlayEl) close(); });
  commands = buildCommands();
  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (overlayEl.classList.contains('open')) close(); else open();
    }
  });
}
function buildCommands() {
  return [
    { name: 'Toggle Grid', keys: 'G', run: () => toggle('grid-toggle') },
    { name: 'Toggle Snap', keys: 'S', run: () => toggle('snap-toggle') },
    { name: 'Toggle Collisions', keys: 'C', run: () => toggle('collision-toggle') },
    { name: 'Toggle Wireframe', run: () => toggle('wireframe-toggle') },
    { name: 'Toggle Shadows', run: () => toggle('shadows-toggle') },
    { name: 'Measure Distance', keys: 'M', run: () => fn.toggleMeasure() },
    { name: 'Draw Wall', keys: 'W', run: () => { if (S.wallMode) fn.exitWallMode(); else fn.enterWallMode(); } },
    { name: 'FPS View', keys: 'P', run: () => fn.toggleFps() },
    { name: 'Screenshot', keys: 'Ctrl+Shift+S', run: () => fn.captureScreenshot() },
    { name: 'Undo', keys: 'Ctrl+Z', run: () => fn.undo() },
    { name: 'Redo', keys: 'Ctrl+Shift+Z', run: () => fn.redo() },
    { name: 'Delete Selected', keys: 'X', run: () => fn.deleteSelected() },
    { name: 'Duplicate Selected', keys: 'Ctrl+D', run: () => fn.duplicateSelected() },
    { name: 'Copy', keys: 'Ctrl+C', run: () => fn.copySelected() },
    { name: 'Paste', keys: 'Ctrl+V', run: () => fn.pasteClipboard() },
    { name: 'Rotate 90°', keys: 'R', run: () => { if (S.selectedTarget) { S.selectedTarget.rotation.y += Math.PI / 2; } } },
    { name: 'Hide Selected', keys: 'H', run: () => fn.hideSelected() },
    { name: 'Unhide All', keys: 'Alt+H', run: () => fn.unhideAll() },
    { name: 'Frame Selected', keys: 'F', run: () => fn.frameSelected() },
    { name: 'Deselect', keys: 'A', run: () => fn.deselectFurniture() },
    { name: 'Front View', keys: '1', run: () => fn.setCameraView('front') },
    { name: 'Right View', keys: '3', run: () => fn.setCameraView('right') },
    { name: 'Top View', keys: '7', run: () => fn.setCameraView('top') },
    { name: 'Toggle Orthographic', keys: '5', run: () => fn.toggleOrtho() },
    { name: 'Export GLB', run: () => document.getElementById('export-glb-btn').click() },
    { name: 'Export JSON', run: () => document.getElementById('export-json-btn').click() },
    { name: 'Load GLB', run: () => document.getElementById('glb-input').click() },
    { name: 'Load JSON', run: () => document.getElementById('json-input').click() },
    { name: 'Load Floor Plan', run: () => document.getElementById('overlay-input').click() },
    { name: 'Clear Layout', run: () => { /* call MCP clear if available */ } },
    { name: 'Toggle Chat', run: () => fn.toggleChat() },
    { name: 'Help', keys: '?', run: () => document.getElementById('help-modal').classList.toggle('open') },
    // furniture placement
    { name: 'Add: Single Bed', cat: 'Furniture', run: () => fn.enterPlaceMode('bed_single') },
    { name: 'Add: Queen Bed', cat: 'Furniture', run: () => fn.enterPlaceMode('bed_queen') },
    { name: 'Add: King Bed', cat: 'Furniture', run: () => fn.enterPlaceMode('bed_king') },
    { name: 'Add: Wardrobe', cat: 'Furniture', run: () => fn.enterPlaceMode('wardrobe') },
    { name: 'Add: Wardrobe S', cat: 'Furniture', run: () => fn.enterPlaceMode('wardrobe_s') },
    { name: 'Add: Bedside Table', cat: 'Furniture', run: () => fn.enterPlaceMode('bedside') },
    { name: 'Add: Dresser', cat: 'Furniture', run: () => fn.enterPlaceMode('dresser') },
    { name: 'Add: 2-Seat Sofa', cat: 'Furniture', run: () => fn.enterPlaceMode('sofa_2') },
    { name: 'Add: 3-Seat Sofa', cat: 'Furniture', run: () => fn.enterPlaceMode('sofa_3') },
    { name: 'Add: L-Sofa', cat: 'Furniture', run: () => fn.enterPlaceMode('sofa_l') },
    { name: 'Add: Coffee Table', cat: 'Furniture', run: () => fn.enterPlaceMode('coffee') },
    { name: 'Add: TV Console', cat: 'Furniture', run: () => fn.enterPlaceMode('tv_console') },
    { name: 'Add: Dining 4-seat', cat: 'Furniture', run: () => fn.enterPlaceMode('dining_4') },
    { name: 'Add: Dining 6-seat', cat: 'Furniture', run: () => fn.enterPlaceMode('dining_6') },
    { name: 'Add: Shoe Rack', cat: 'Furniture', run: () => fn.enterPlaceMode('shoe_rack') },
    { name: 'Add: Fridge', cat: 'Furniture', run: () => fn.enterPlaceMode('fridge') },
    { name: 'Add: Washer', cat: 'Furniture', run: () => fn.enterPlaceMode('washer') },
    { name: 'Add: Kitchen Counter', cat: 'Furniture', run: () => fn.enterPlaceMode('kitchen_counter') },
    { name: 'Add: Sink', cat: 'Furniture', run: () => fn.enterPlaceMode('sink') },
    { name: 'Add: Toilet', cat: 'Furniture', run: () => fn.enterPlaceMode('toilet') },
    { name: 'Add: Shower', cat: 'Furniture', run: () => fn.enterPlaceMode('shower') },
    { name: 'Add: Desk', cat: 'Furniture', run: () => fn.enterPlaceMode('desk') },
    { name: 'Add: L-Desk', cat: 'Furniture', run: () => fn.enterPlaceMode('desk_l') },
    { name: 'Add: Bookshelf', cat: 'Furniture', run: () => fn.enterPlaceMode('bookshelf') },
    { name: 'Add: Office Chair', cat: 'Furniture', run: () => fn.enterPlaceMode('chair') },
  ];
}
let selectedIdx = 0;
function render(query) {
  const q = query.toLowerCase().trim();
  const filtered = q ? commands.filter(c => c.name.toLowerCase().includes(q) || (c.cat || '').toLowerCase().includes(q)) : commands;
  selectedIdx = 0;
  listEl.innerHTML = '';
  for (let i = 0; i < Math.min(filtered.length, 20); i++) {
    const c = filtered[i];
    const row = document.createElement('div');
    row.className = 'cmd-row' + (i === 0 ? ' active' : '');
    row.innerHTML = `<span class="cmd-name">${c.name}</span>${c.keys ? `<span class="cmd-keys">${c.keys}</span>` : ''}`;
    row.addEventListener('click', () => { execute(c); });
    row.addEventListener('mouseenter', () => {
      listEl.querySelector('.cmd-row.active')?.classList.remove('active');
      row.classList.add('active');
      selectedIdx = i;
    });
    listEl.appendChild(row);
  }
  listEl._filtered = filtered;
}
function onKey(e) {
  const rows = listEl.querySelectorAll('.cmd-row');
  if (e.key === 'ArrowDown') { e.preventDefault(); move(1, rows); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1, rows); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    const filtered = listEl._filtered || commands;
    if (filtered[selectedIdx]) execute(filtered[selectedIdx]);
  }
  else if (e.key === 'Escape') { close(); }
}
function move(dir, rows) {
  rows[selectedIdx]?.classList.remove('active');
  selectedIdx = Math.max(0, Math.min(rows.length - 1, selectedIdx + dir));
  rows[selectedIdx]?.classList.add('active');
  rows[selectedIdx]?.scrollIntoView({ block: 'nearest' });
}
function execute(cmd) {
  close();
  cmd.run();
}
function open() {
  overlayEl.classList.add('open');
  inputEl.value = '';
  render('');
  inputEl.focus();
}
function close() {
  overlayEl.classList.remove('open');
}
function toggle(id) {
  const cb = document.getElementById(id);
  cb.checked = !cb.checked;
  cb.dispatchEvent(new Event('change'));
}
