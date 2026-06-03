import { S, fn } from './state.js';
export function initContextMenu() {
  const menu = document.getElementById('context-menu');
  document.addEventListener('contextmenu', (e) => {
    if (e.target.tagName === 'INPUT') return;
    e.preventDefault();
    if (S.fpsMode || S.wallMode || S.placeMode) return;
    const items = menu.querySelectorAll('[data-action]');
    const hasSel = !!S.selectedTarget;
    const hasClip = !!S.clipboard;
    items.forEach(el => {
      const a = el.dataset.action;
      if (a === 'paste') el.style.display = hasClip ? '' : 'none';
      else if (a !== 'paste') el.style.display = (a === 'select-all' || hasSel) ? '' : 'none';
    });
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';
    menu.classList.add('open');
  });
  document.addEventListener('click', () => menu.classList.remove('open'));
  menu.addEventListener('click', (e) => {
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (!action) return;
    menu.classList.remove('open');
    switch (action) {
      case 'delete': fn.deleteSelected(); break;
      case 'duplicate': fn.duplicateSelected(); break;
      case 'copy': fn.copySelected(); break;
      case 'paste': fn.pasteClipboard(); break;
      case 'rotate': if (S.selectedTarget) {
        const old = S.selectedTarget.rotation.y;
        S.selectedTarget.rotation.y += Math.PI / 2;
        if (S.collisionEnabled && fn.checkCollision(S.selectedTarget)) { S.selectedTarget.rotation.y = old; fn.showCollisionFlash(); }
        else fn.pushUndo({ type: 'rotate', mesh: S.selectedTarget, oldRot: old, newRot: S.selectedTarget.rotation.y });
      } break;
      case 'hide': fn.hideSelected(); break;
      case 'frame': fn.frameSelected(); break;
      case 'select-all': if (S.selectedTarget) fn.deselectFurniture(); else fn.frameSelected(); break;
    }
  });
}
