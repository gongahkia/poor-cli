import * as THREE from 'three';
import { S, fn } from './state.js';
import { FURNITURE_NAMES } from './furniture.js';
export function initSceneList() {
  fn.refreshSceneList = refreshSceneList;
  document.getElementById('scene-filter')?.addEventListener('input', refreshSceneList);
  document.getElementById('scene-filter-kind')?.addEventListener('change', refreshSceneList);
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
  return '#b3b3b3';
}
function frameBounds(box) {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  return { center, dist: Math.max(size.x, size.y, size.z, 1) * 1.5 };
}
function warningMatches(mesh, label) {
  const meta = mesh.userData.layoutMeta || {};
  const id = meta.id || mesh.userData.name || label;
  const warnings = S.validationReport?.warnings || [];
  return warnings.filter((warning) => {
    const geom = warning.geometry || {};
    const ids = [geom.item_id, ...(geom.item_ids || [])].filter(Boolean).map(String);
    if (ids.includes(String(id))) return true;
    const haystack = `${warning.message || ''} ${warning.explanation || ''} ${warning.room || ''}`.toLowerCase();
    return haystack.includes(String(label || '').toLowerCase()) || (mesh.userData.room && haystack.includes(String(mesh.userData.room).toLowerCase()));
  });
}
function statusFor(mesh) {
  const meta = mesh.userData.layoutMeta || {};
  if (meta.scenario_status) return meta.scenario_status;
  if (meta.removed) return 'removed';
  if (meta.proposed) return 'proposed';
  return 'existing';
}
function sceneSearchText(mesh, label, warnings) {
  const meta = mesh.userData.layoutMeta || {};
  return [
    label,
    mesh.userData.room,
    mesh.userData.furnitureType,
    mesh.userData.isWall ? 'wall' : '',
    mesh.userData.isModelPart ? 'model' : '',
    statusFor(mesh),
    meta.locked || meta.do_not_touch ? 'locked' : '',
    warnings.length ? 'warning' : '',
    meta.source,
    meta.source_url,
  ].filter(Boolean).join(' ').toLowerCase();
}
function includeMesh(mesh, label, warnings) {
  const query = (document.getElementById('scene-filter')?.value || '').trim().toLowerCase();
  const kind = document.getElementById('scene-filter-kind')?.value || '';
  const meta = mesh.userData.layoutMeta || {};
  if (query && !sceneSearchText(mesh, label, warnings).includes(query)) return false;
  if (kind === 'warning' && !warnings.length) return false;
  if (kind === 'locked' && !(meta.locked || meta.do_not_touch)) return false;
  if (['existing', 'proposed', 'removed'].includes(kind) && statusFor(mesh) !== kind) return false;
  return true;
}
function refreshSceneList() {
  const list = document.getElementById('scene-list');
  const count = document.getElementById('scene-count');
  list.innerHTML = '';
  let visibleCount = 0;
  for (const m of S.draggables) {
    const label = getLabel(m);
    const warnings = warningMatches(m, label);
    if (!includeMesh(m, label, warnings)) continue;
    visibleCount += 1;
    const row = document.createElement('div');
    const isSel = m === S.selectedTarget || S.multiSelected.includes(m);
    row.className = 'scene-item' + (isSel ? ' active' : '') + (!m.visible ? ' hidden-item' : '');
    const swatch = document.createElement('span');
    swatch.className = 'si-color'; swatch.style.background = getColor(m);
    row.appendChild(swatch);
    const name = document.createElement('span');
    name.className = 'si-name'; name.textContent = label;
    row.appendChild(name);
    if (warnings.length) {
      const badge = document.createElement('span');
      badge.className = `si-badge si-warning ${warnings.some((warning) => warning.severity === 'blocked' || warning.severity === 'serious') ? 'si-warning-hot' : ''}`;
      badge.textContent = warnings[0].severity || 'warning';
      badge.title = warnings.map((warning) => warning.message).join('\n');
      row.appendChild(badge);
    }
    const status = statusFor(m);
    if (status !== 'existing') {
      const badge = document.createElement('span');
      badge.className = `si-badge si-status si-${status}`;
      badge.textContent = status;
      row.appendChild(badge);
    }
    const confidence = m.userData.layoutMeta?.confidence;
    if (confidence) {
      const badge = document.createElement('span');
      badge.className = 'si-badge';
      badge.textContent = confidence;
      row.appendChild(badge);
    }
    if (m.userData.layoutMeta?.locked || m.userData.layoutMeta?.do_not_touch) {
      const lock = document.createElement('span');
      lock.className = 'si-badge si-lock';
      lock.textContent = 'locked';
      row.appendChild(lock);
    }
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
  count.textContent = '(' + visibleCount + '/' + S.draggables.length + ')';
}
