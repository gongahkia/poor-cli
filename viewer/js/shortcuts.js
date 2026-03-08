import { S, fn } from './state.js';
export function initShortcuts() {
  window.addEventListener('keydown', (e) => {
    const key = e.key.toLowerCase();
    const inInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT';
    // undo/redo always available (but not inside text inputs)
    if (!inInput && key === 'z' && (e.ctrlKey || e.metaKey) && e.shiftKey) { e.preventDefault(); fn.redo(); return; }
    if (!inInput && key === 'z' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fn.undo(); return; }
    if (!inInput && key === 'y' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fn.redo(); return; }
    if (inInput) return;
    // FPS mode: only ESC to exit
    if (S.fpsMode) { if (key === 'escape') fn.exitFps(); return; }
    if (key === 'escape') {
      if (S.placeMode) fn.cancelPlaceMode();
      else if (S.wallMode) fn.exitWallMode();
      return;
    }
    if (key === 'w') { if (S.wallMode) fn.exitWallMode(); else fn.enterWallMode(); return; }
    if (S.wallMode) return;
    if (key === 'p') { fn.toggleFps(); return; }
    if (key === 's' && (e.ctrlKey || e.metaKey) && e.shiftKey) { e.preventDefault(); fn.captureScreenshot(); }
    else if (key === 'g') { toggle('grid-toggle'); }
    else if (key === 's' && !(e.ctrlKey || e.metaKey)) { toggle('snap-toggle'); }
    else if (key === 'c' && !(e.ctrlKey || e.metaKey)) { toggle('collision-toggle'); }
    else if (key === 'r' && S.selectedTarget) {
      const step = e.shiftKey ? (Math.PI / 12) : (Math.PI / 2);
      const targets = [S.selectedTarget, ...S.multiSelected];
      for (const mesh of targets) {
        const oldRot = mesh.rotation.y;
        mesh.rotation.y += step;
        if (S.collisionEnabled && fn.checkCollision(mesh, new Set(targets))) {
          mesh.rotation.y = oldRot; fn.showCollisionFlash(); return;
        }
        fn.pushUndo({ type: 'rotate', mesh, oldRot, newRot: mesh.rotation.y });
      }
    }
    else if ((key === 'x' || key === 'delete' || key === 'backspace') && S.selectedTarget) { fn.deleteSelected(); }
    else if (key === 'c' && (e.ctrlKey || e.metaKey) && !e.shiftKey) { e.preventDefault(); fn.copySelected(); }
    else if (key === 'v' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fn.pasteClipboard(); }
    else if (key === 'd' && (e.ctrlKey || e.metaKey || e.shiftKey)) { e.preventDefault(); fn.duplicateSelected(); }
    else if (key === 'h' && e.altKey) { fn.unhideAll(); }
    else if (key === 'h') { fn.hideSelected(); }
    else if (key === 'f') { fn.frameSelected(); }
    else if (key === 'a') { if (S.selectedTarget) fn.deselectFurniture(); else fn.frameSelected(); }
    else if (key === '1') { fn.setCameraView('front'); }
    else if (key === '3') { fn.setCameraView('right'); }
    else if (key === '7') { fn.setCameraView('top'); }
    else if (key === '5') { fn.toggleOrtho(); }
    else if (key === '?') { toggleHelp(); }
  });
  document.getElementById('help-btn').addEventListener('click', toggleHelp);
  document.getElementById('help-close').addEventListener('click', () => {
    document.getElementById('help-modal').classList.remove('open');
  });
}
function toggle(id) {
  const cb = document.getElementById(id);
  cb.checked = !cb.checked;
  cb.dispatchEvent(new Event('change'));
}
function toggleHelp() {
  document.getElementById('help-modal').classList.toggle('open');
}
