// view router — toggles .view-panel elements by data-view attribute
// supports split view: drag a sidebar nav item onto the main area to split
const views = {};
let current = 'chat';
let splitState = null;
let _draggedView = null;
let _isDragging = false; // prevents click handler from firing after drag

export function registerView(name, initFn) { views[name] = { initFn, initialized: false }; }

export function showView(name) {
  if (_isDragging) { console.log('[split] showView blocked — drag in progress'); return; }
  if (splitState) unsplit();
  _activateView(name);
  current = name;
}

export function currentView() { return current; }

function _activateView(name) {
  document.querySelectorAll('.view-panel').forEach(el => el.hidden = el.dataset.view !== name);
  _ensureInit(name);
  document.querySelectorAll('.sidebar-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.nav === name);
  });
}

function _ensureInit(name) {
  if (views[name] && !views[name].initialized) {
    views[name].initFn();
    views[name].initialized = true;
  }
}

// ── split view ──────────────────────────────────────────────────────

export function showSplit(secondaryName, direction) {
  console.log(`[split] showSplit called: secondary=${secondaryName}, dir=${direction}, current=${current}`);
  if (secondaryName === current) { console.log('[split] aborted — same view'); return; }
  const mainPanel = document.querySelector('.main-panel');
  if (!mainPanel) { console.log('[split] aborted — no .main-panel'); return; }
  if (splitState) unsplit();
  splitState = { direction, primary: current, secondary: secondaryName };
  const wrapper = document.createElement('div');
  wrapper.id = 'split-wrapper';
  wrapper.className = `split-wrapper split-${direction}`;
  const primaryPane = document.createElement('div');
  primaryPane.className = 'split-pane split-pane-primary';
  const secondaryPane = document.createElement('div');
  secondaryPane.className = 'split-pane split-pane-secondary';
  const divider = document.createElement('div');
  divider.className = 'split-divider';
  divider.innerHTML = `<button class="split-unsplit-btn" title="Close split">&times;</button>`;
  divider.querySelector('.split-unsplit-btn').onclick = (e) => { e.stopPropagation(); unsplit(); };
  divider.addEventListener('mousedown', (e) => {
    if (e.target.closest('.split-unsplit-btn')) return;
    e.preventDefault();
    const isH = direction === 'horizontal';
    const startPos = isH ? e.clientX : e.clientY;
    const startSize = isH ? primaryPane.offsetWidth : primaryPane.offsetHeight;
    const onMove = (ev) => {
      const delta = (isH ? ev.clientX : ev.clientY) - startPos;
      const total = isH ? wrapper.offsetWidth : wrapper.offsetHeight;
      const pct = Math.min(80, Math.max(20, ((startSize + delta) / total) * 100));
      primaryPane.style.flex = `0 0 ${pct}%`;
      secondaryPane.style.flex = `0 0 ${100 - pct}%`;
    };
    const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
  const primaryView = mainPanel.querySelector(`.view-panel[data-view="${current}"]`);
  const secondaryView = mainPanel.querySelector(`.view-panel[data-view="${secondaryName}"]`);
  if (!primaryView || !secondaryView) {
    console.log(`[split] aborted — missing panels: primary=${!!primaryView} secondary=${!!secondaryView}`);
    splitState = null;
    return;
  }
  primaryPane.appendChild(primaryView);
  secondaryPane.appendChild(secondaryView);
  primaryView.hidden = false;
  secondaryView.hidden = false;
  _ensureInit(secondaryName);
  wrapper.appendChild(primaryPane);
  wrapper.appendChild(divider);
  wrapper.appendChild(secondaryPane);
  const anchor = mainPanel.querySelector('#workspace-bar');
  if (anchor && anchor.nextSibling) mainPanel.insertBefore(wrapper, anchor.nextSibling);
  else mainPanel.appendChild(wrapper);
  mainPanel.querySelectorAll(':scope > .view-panel').forEach(el => { el.hidden = true; });
  document.querySelectorAll('.sidebar-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.nav === current || el.dataset.nav === secondaryName);
  });
  console.log('[split] split applied successfully');
}

export function unsplit() {
  if (!splitState) return;
  console.log('[split] unsplit');
  const mainPanel = document.querySelector('.main-panel');
  const wrapper = document.getElementById('split-wrapper');
  if (!wrapper || !mainPanel) { splitState = null; return; }
  const panels = wrapper.querySelectorAll('.view-panel');
  const statusBar = mainPanel.querySelector('footer');
  panels.forEach(p => {
    if (statusBar) mainPanel.insertBefore(p, statusBar);
    else mainPanel.appendChild(p);
  });
  wrapper.remove();
  const restoreTo = splitState.primary;
  splitState = null;
  _activateView(restoreTo);
  current = restoreTo;
}

// ── drag & drop ─────────────────────────────────────────────────────

export function initSplitDragDrop() {
  console.log('[split] initSplitDragDrop — setting up drag on sidebar items');
  const items = document.querySelectorAll('.sidebar-nav-item');
  console.log(`[split] found ${items.length} sidebar items`);
  items.forEach(el => {
    if (!el.dataset.nav) return;
    el.draggable = true;
    el.addEventListener('dragstart', (e) => {
      _draggedView = el.dataset.nav;
      _isDragging = true;
      e.dataTransfer.setData('text/plain', el.dataset.nav);
      e.dataTransfer.effectAllowed = 'move';
      console.log(`[split] dragstart: view=${_draggedView}`);
      setTimeout(() => _showDropZones(), 0);
    });
    el.addEventListener('dragend', () => {
      console.log(`[split] dragend: view=${_draggedView}`);
      _draggedView = null;
      _hideDropZones();
      // delay clearing _isDragging so the click handler doesn't fire
      setTimeout(() => { _isDragging = false; }, 100);
    });
  });
  // also allow dropping on the main panel itself as a fallback
  const mainPanel = document.querySelector('.main-panel');
  if (mainPanel) {
    mainPanel.addEventListener('dragover', (e) => {
      if (_draggedView) e.preventDefault();
    });
    mainPanel.addEventListener('drop', (e) => {
      if (!_draggedView) return;
      e.preventDefault();
      console.log(`[split] drop on main-panel fallback: view=${_draggedView}`);
      const viewName = _draggedView;
      _draggedView = null;
      _hideDropZones();
      if (viewName && viewName !== current) {
        showSplit(viewName, 'horizontal');
      }
      setTimeout(() => { _isDragging = false; }, 100);
    });
  }
}

function _showDropZones() {
  _hideDropZones();
  const mainPanel = document.querySelector('.main-panel');
  if (!mainPanel) { console.log('[split] _showDropZones — no main-panel'); return; }
  console.log('[split] showing drop zones');
  const overlay = document.createElement('div');
  overlay.id = 'split-drop-overlay';
  mainPanel.style.position = 'relative';
  mainPanel.appendChild(overlay);
  const zones = [
    { cls: 'split-drop-left', dir: 'horizontal', side: 'left', label: 'Left' },
    { cls: 'split-drop-right', dir: 'horizontal', side: 'right', label: 'Right' },
    { cls: 'split-drop-top', dir: 'vertical', side: 'top', label: 'Top' },
    { cls: 'split-drop-bottom', dir: 'vertical', side: 'bottom', label: 'Bottom' },
  ];
  zones.forEach(z => {
    const zone = document.createElement('div');
    zone.className = `split-drop-zone ${z.cls}`;
    zone.dataset.dir = z.dir;
    zone.dataset.side = z.side;
    zone.innerHTML = `<span>${z.label}</span>`;
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = 'move';
      zone.classList.add('active');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('active'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const viewName = _draggedView;
      console.log(`[split] DROP on zone ${z.side}: view=${viewName}, current=${current}`);
      _draggedView = null;
      _hideDropZones();
      if (!viewName || viewName === current) {
        console.log('[split] drop ignored — same view or no view');
        setTimeout(() => { _isDragging = false; }, 100);
        return;
      }
      if (z.side === 'right' || z.side === 'bottom') {
        showSplit(viewName, z.dir);
      } else {
        const oldCurrent = current;
        current = viewName;
        _ensureInit(viewName);
        showSplit(oldCurrent, z.dir);
      }
      setTimeout(() => { _isDragging = false; }, 100);
    });
    overlay.appendChild(zone);
  });
  // verify overlay is visible
  const rect = overlay.getBoundingClientRect();
  console.log(`[split] overlay rect: ${rect.width}x${rect.height} at (${rect.left},${rect.top})`);
}

function _hideDropZones() {
  const old = document.getElementById('split-drop-overlay');
  if (old) { old.remove(); console.log('[split] drop zones removed'); }
}
