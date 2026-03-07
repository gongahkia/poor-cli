import { S, fn } from './state.js';
export function initShortcuts() {
  window.addEventListener('keydown', (e) => {
    const key = e.key.toLowerCase();
    if (e.target.tagName === 'INPUT') return;
    // undo/redo always available
    if (key === 'z' && (e.ctrlKey || e.metaKey) && e.shiftKey) { e.preventDefault(); fn.redo(); return; }
    if (key === 'z' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fn.undo(); return; }
    if (key === 'y' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fn.redo(); return; }
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
      const oldRot = S.selectedTarget.rotation.y;
      const step = e.shiftKey ? (Math.PI / 12) : (Math.PI / 2);
      S.selectedTarget.rotation.y += step;
      if (S.collisionEnabled && fn.checkCollision(S.selectedTarget)) {
        S.selectedTarget.rotation.y = oldRot; fn.showCollisionFlash(); return;
      }
      fn.pushUndo({ type: 'rotate', mesh: S.selectedTarget, oldRot, newRot: S.selectedTarget.rotation.y });
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
