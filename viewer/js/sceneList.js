import * as THREE from 'three';
import { S, fn } from './state.js';
import { FURNITURE_NAMES } from './furniture.js';
export function initSceneList() {
  fn.refreshSceneList = refreshSceneList;
}
function getLabel(mesh) {
  if (mesh.userData.name) return mesh.userData.name;
  if (mesh.userData.furnitureType) return FURNITURE_NAMES[mesh.userData.furnitureType] || mesh.userData.furnitureType;
  if (mesh.userData.isWall) return 'Wall';
  if (mesh.userData.isModelPart) return 'Model Part';
  return 'Object';
}
function getColor(mesh) {
  if (mesh.material && mesh.material.color) return '#' + mesh.material.color.getHexString();
  return '#888';
}
function frameBounds(box) {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  return { center, dist: Math.max(size.x, size.y, size.z, 1) * 1.5 };
}
function refreshSceneList() {
  const list = document.getElementById('scene-list');
  const count = document.getElementById('scene-count');
  list.innerHTML = '';
  count.textContent = '(' + S.draggables.length + ')';
  for (const m of S.draggables) {
    const row = document.createElement('div');
    const isSel = m === S.selectedTarget || S.multiSelected.includes(m);
    row.className = 'scene-item' + (isSel ? ' active' : '') + (!m.visible ? ' hidden-item' : '');
    const swatch = document.createElement('span');
    swatch.className = 'si-color'; swatch.style.background = getColor(m);
    row.appendChild(swatch);
    const name = document.createElement('span');
    name.className = 'si-name'; name.textContent = getLabel(m);
    row.appendChild(name);
    const visBtn = document.createElement('button');
    visBtn.className = 'si-btn'; visBtn.textContent = m.visible ? 'V' : '-'; visBtn.title = m.visible ? 'Hide' : 'Show';
    visBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (m.visible) { m.visible = false; if (!S.hiddenObjects.includes(m)) S.hiddenObjects.push(m); if (m === S.selectedTarget) fn.deselectFurniture(); }
      else { m.visible = true; const hi = S.hiddenObjects.indexOf(m); if (hi >= 0) S.hiddenObjects.splice(hi, 1); }
      refreshSceneList();
    });
    row.appendChild(visBtn);
    const frameBtn = document.createElement('button');
    frameBtn.className = 'si-btn'; frameBtn.textContent = 'F'; frameBtn.title = 'Frame';
    frameBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fn.selectFurniture(m);
      const { center, dist } = frameBounds(new THREE.Box3().setFromObject(m));
      const dir = S.camera.position.clone().sub(S.orbit.target).normalize();
      S.orbit.target.copy(center);
      S.camera.position.copy(center).addScaledVector(dir, dist);
      S.orbit.update(); refreshSceneList();
    });
    row.appendChild(frameBtn);
    const delBtn = document.createElement('button');
    delBtn.className = 'si-btn'; delBtn.textContent = 'X'; delBtn.title = 'Delete';
    delBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (m === S.selectedTarget) { fn.deleteSelected(); }
      else {
        fn.pushUndo({ type: 'delete', mesh: m, inUserWalls: S.userWalls.includes(m), inModelParts: S.modelParts.includes(m) });
        S.scene.remove(m);
        const di = S.draggables.indexOf(m); if (di >= 0) S.draggables.splice(di, 1);
        const wi = S.userWalls.indexOf(m); if (wi >= 0) S.userWalls.splice(wi, 1);
        const mi = S.modelParts.indexOf(m); if (mi >= 0) S.modelParts.splice(mi, 1);
      }
      refreshSceneList();
    });
    row.appendChild(delBtn);
    row.addEventListener('click', () => { if (m.visible) { fn.selectFurniture(m); refreshSceneList(); } });
    list.appendChild(row);
  }
}
