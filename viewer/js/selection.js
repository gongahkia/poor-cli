import * as THREE from 'three';
import { S, fn, SIDEBAR_W } from './state.js';
const outlineMat = new THREE.LineBasicMaterial({ color: 0x44ddaa, linewidth: 2 });
const multiOutlineMat = new THREE.LineBasicMaterial({ color: 0x44aadd, linewidth: 2 });
let resizeOldDims = null;
export function initSelection() {
  fn.selectFurniture = selectFurniture;
  fn.deselectFurniture = deselectFurniture;
  fn.deleteSelected = deleteSelected;
  fn.populateDimSliders = populateDimSliders;
  fn.refreshOutline = refreshOutline;
  fn.getMeshDims = getMeshDims;
  fn.resizeSelected = resizeSelected;
  fn.duplicateSelected = duplicateSelected;
  fn.hideSelected = hideSelected;
  fn.unhideAll = unhideAll;
  fn.getGroundPoint = getGroundPoint;
  fn.copySelected = copySelected;
  fn.pasteClipboard = pasteClipboard;
  fn.toggleMultiSelect = toggleMultiSelect;
  fn.clearMultiSelect = clearMultiSelect;
  setupDimSliders();
  setupColorPicker();
  setupDragHandlers();
  document.getElementById('delete-btn').addEventListener('click', deleteSelected);
}
function refreshOutline(mesh) {
  const old = mesh.getObjectByName('_outline');
  if (old) mesh.remove(old);
  const edges = new THREE.EdgesGeometry(mesh.geometry);
  const o = new THREE.LineSegments(edges, outlineMat);
  o.name = '_outline';
  mesh.add(o);
}
function addMultiOutline(mesh) {
  if (mesh.getObjectByName('_outline')) return; // already primary
  if (mesh.getObjectByName('_multi_outline')) return;
  const edges = new THREE.EdgesGeometry(mesh.geometry);
  const o = new THREE.LineSegments(edges, multiOutlineMat);
  o.name = '_multi_outline';
  mesh.add(o);
}
function removeMultiOutline(mesh) {
  const ol = mesh.getObjectByName('_multi_outline');
  if (ol) mesh.remove(ol);
}
function getMeshDims(mesh) {
  const p = mesh.geometry.parameters;
  if (p && p.width !== undefined) return { w: p.width, h: p.height, d: p.depth };
  const box = new THREE.Box3().setFromBufferAttribute(mesh.geometry.attributes.position);
  const size = box.getSize(new THREE.Vector3());
  return { w: size.x, h: size.y, d: size.z };
}
function selectFurniture(mesh) {
  deselectFurniture();
  S.selectedTarget = mesh;
  refreshOutline(mesh);
  document.getElementById('selected-info').style.display = '';
  populateDimSliders(mesh);
  updateColorPicker(mesh);
  updatePosDisplay(mesh);
  fn.refreshSceneList();
}
function toggleMultiSelect(mesh) {
  if (mesh === S.selectedTarget) return; // already primary
  const idx = S.multiSelected.indexOf(mesh);
  if (idx >= 0) {
    S.multiSelected.splice(idx, 1);
    removeMultiOutline(mesh);
  } else {
    if (!S.selectedTarget) {
      selectFurniture(mesh);
      return;
    }
    S.multiSelected.push(mesh);
    addMultiOutline(mesh);
  }
  fn.refreshSceneList();
}
function clearMultiSelect() {
  for (const m of S.multiSelected) removeMultiOutline(m);
  S.multiSelected.length = 0;
}
function allSelected() {
  const arr = [];
  if (S.selectedTarget) arr.push(S.selectedTarget);
  arr.push(...S.multiSelected);
  return arr;
}
function deselectFurniture() {
  if (S.selectedTarget) {
    const ol = S.selectedTarget.getObjectByName('_outline');
    if (ol) S.selectedTarget.remove(ol);
    S.selectedTarget = null;
  }
  clearMultiSelect();
  document.getElementById('selected-info').style.display = 'none';
  fn.refreshSceneList();
}
function deleteSelected() {
  const targets = allSelected();
  if (targets.length === 0) return;
  for (const mesh of targets) {
    fn.pushUndo({ type: 'delete', mesh, inUserWalls: S.userWalls.includes(mesh), inModelParts: S.modelParts.includes(mesh) });
    S.scene.remove(mesh);
    rm(S.draggables, mesh); rm(S.userWalls, mesh); rm(S.modelParts, mesh);
  }
  S.selectedTarget = null;
  S.multiSelected.length = 0;
  document.getElementById('selected-info').style.display = 'none';
  fn.refreshSceneList();
}
function duplicateSelected() {
  const targets = allSelected();
  if (targets.length === 0) return;
  const clones = [];
  const offset = S.snapEnabled ? (1.0 / S.gridDivisions) : 0.5;
  for (const mesh of targets) {
    const clone = mesh.clone();
    clone.position.x += offset;
    clone.position.z += offset;
    clone.userData = { ...mesh.userData };
    S.scene.add(clone);
    if (fn.checkCollision(clone)) { S.scene.remove(clone); fn.showCollisionFlash(); continue; }
    S.draggables.push(clone);
    if (mesh.userData.isWall) S.userWalls.push(clone);
    fn.pushUndo({ type: 'add', mesh: clone, inUserWalls: !!clone.userData.isWall });
    clones.push(clone);
  }
  if (clones.length > 0) {
    deselectFurniture();
    selectFurniture(clones[0]);
    for (let i = 1; i < clones.length; i++) toggleMultiSelect(clones[i]);
  }
}
function hideSelected() {
  const targets = allSelected();
  if (targets.length === 0) return;
  for (const mesh of targets) {
    mesh.visible = false;
    if (!S.hiddenObjects.includes(mesh)) S.hiddenObjects.push(mesh);
  }
  deselectFurniture();
}
function unhideAll() {
  for (const obj of S.hiddenObjects) obj.visible = true;
  S.hiddenObjects.length = 0;
  fn.refreshSceneList();
}
function getGroundPoint(e) {
  S.mouse.x = (e.clientX / (innerWidth - SIDEBAR_W)) * 2 - 1;
  S.mouse.y = -(e.clientY / innerHeight) * 2 + 1;
  S.raycaster.setFromCamera(S.mouse, S.camera);
  const pt = new THREE.Vector3();
  S.raycaster.ray.intersectPlane(S.dragPlane, pt);
  pt.x = fn.snapToGrid(pt.x); pt.z = fn.snapToGrid(pt.z); pt.y = 0;
  return pt;
}
function resizeSelected(newW, newH, newD) {
  if (!S.selectedTarget) return;
  const mesh = S.selectedTarget;
  const oldGeo = mesh.geometry, oldY = mesh.position.y, oldBaseY = mesh.userData.baseY;
  mesh.geometry = new THREE.BoxGeometry(newW, newH, newD);
  mesh.position.y = newH / 2; mesh.userData.baseY = newH / 2;
  if (S.collisionEnabled && fn.checkCollision(mesh)) {
    mesh.geometry.dispose(); mesh.geometry = oldGeo;
    mesh.position.y = oldY; mesh.userData.baseY = oldBaseY;
    populateDimSliders(mesh); fn.showCollisionFlash(); return;
  }
  oldGeo.dispose();
  if (mesh.getObjectByName('_outline')) refreshOutline(mesh);
}
function populateDimSliders(mesh) {
  const d = getMeshDims(mesh);
  document.getElementById('sel-width').value = Math.round(d.w * 10);
  document.getElementById('sel-width-num').value = d.w.toFixed(2);
  document.getElementById('sel-height').value = Math.round(d.h * 10);
  document.getElementById('sel-height-num').value = d.h.toFixed(2);
  document.getElementById('sel-depth').value = Math.round(d.d * 10);
  document.getElementById('sel-depth-num').value = d.d.toFixed(2);
}
function setupDimSliders() {
  const axes = [
    { sl: 'sel-width', num: 'sel-width-num', apply: (v, d) => resizeSelected(v, d.h, d.d) },
    { sl: 'sel-height', num: 'sel-height-num', apply: (v, d) => resizeSelected(d.w, v, d.d) },
    { sl: 'sel-depth', num: 'sel-depth-num', apply: (v, d) => resizeSelected(d.w, d.h, v) },
  ];
  for (const { sl, num, apply } of axes) {
    const slider = document.getElementById(sl), numEl = document.getElementById(num);
    slider.addEventListener('pointerdown', () => { if (S.selectedTarget) resizeOldDims = getMeshDims(S.selectedTarget); });
    slider.addEventListener('pointerup', endResize);
    slider.addEventListener('input', () => {
      if (!S.selectedTarget) return;
      const d = getMeshDims(S.selectedTarget), nv = parseInt(slider.value) / 10;
      numEl.value = nv.toFixed(2); apply(nv, d);
    });
    numEl.addEventListener('change', () => {
      if (!S.selectedTarget) return;
      resizeOldDims = getMeshDims(S.selectedTarget);
      const d = getMeshDims(S.selectedTarget);
      const nv = Math.max(0.05, Math.min(20, parseFloat(numEl.value) || 0.05));
      numEl.value = nv.toFixed(2); slider.value = Math.round(nv * 10);
      apply(nv, d); endResize();
    });
  }
}
function endResize() {
  if (S.selectedTarget && resizeOldDims) {
    const nd = getMeshDims(S.selectedTarget);
    if (resizeOldDims.w !== nd.w || resizeOldDims.h !== nd.h || resizeOldDims.d !== nd.d) {
      fn.pushUndo({ type: 'resize', mesh: S.selectedTarget, oldDims: resizeOldDims, newDims: nd, oldY: resizeOldDims.h / 2, newY: nd.h / 2 });
    }
  }
  resizeOldDims = null;
}
function setupColorPicker() {
  const picker = document.getElementById('sel-color');
  if (!picker) return;
  picker.addEventListener('input', () => {
    if (!S.selectedTarget || !S.selectedTarget.material) return;
    const oldColor = S.selectedTarget.material.color.getHex();
    const newColor = parseInt(picker.value.slice(1), 16);
    S.selectedTarget.material.color.setHex(newColor);
    fn.pushUndo({ type: 'color', mesh: S.selectedTarget, oldColor, newColor });
    fn.refreshSceneList();
  });
}
function updateColorPicker(mesh) {
  const picker = document.getElementById('sel-color');
  if (!picker || !mesh.material || !mesh.material.color) return;
  picker.value = '#' + mesh.material.color.getHexString();
}
function updatePosDisplay(mesh) {
  const el = document.getElementById('sel-pos');
  if (!el) return;
  const p = mesh.position;
  el.textContent = `${p.x.toFixed(2)}, ${p.y.toFixed(2)}, ${p.z.toFixed(2)}`;
}
let multiDragStarts = null;
function setupDragHandlers() {
  const canvas = S.renderer.domElement;
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || S.fpsMode) return;
    if (S.placeMode) { fn.confirmPlacement(); return; }
    if (S.wallMode) {
      const pt = getGroundPoint(e);
      if (!S.wallStart) {
        S.wallStart = pt.clone();
        document.getElementById('wall-status').textContent = 'Click to place wall end point...';
      } else {
        fn.placeWall(pt);
        if (S.wallPreview) { S.scene.remove(S.wallPreview); S.wallPreview = null; }
        S.wallStart = pt.clone();
        document.getElementById('wall-status').textContent = 'Click next point or Esc to stop...';
      }
      return;
    }
    if (S.measureMode) { fn.measureClick(e); return; }
    S.mouse.x = (e.clientX / (innerWidth - SIDEBAR_W)) * 2 - 1;
    S.mouse.y = -(e.clientY / innerHeight) * 2 + 1;
    S.raycaster.setFromCamera(S.mouse, S.camera);
    const hits = S.raycaster.intersectObjects(S.draggables);
    if (hits.length > 0) {
      const hit = hits[0].object;
      if (e.shiftKey) {
        toggleMultiSelect(hit);
        return;
      }
      // if clicking an already multi-selected object, make it the drag target
      const isMulti = S.multiSelected.includes(hit) || hit === S.selectedTarget;
      if (!isMulti) {
        clearMultiSelect();
        selectFurniture(hit);
      }
      S.dragTarget = hit;
      S.dragStartPos = hit.position.clone();
      // capture multi-select start positions for group drag
      if (S.multiSelected.length > 0) {
        multiDragStarts = new Map();
        if (S.selectedTarget) multiDragStarts.set(S.selectedTarget, S.selectedTarget.position.clone());
        for (const m of S.multiSelected) multiDragStarts.set(m, m.position.clone());
      } else {
        multiDragStarts = null;
      }
      if (!isMulti) selectFurniture(hit);
      S.orbit.enabled = false;
      const ix = new THREE.Vector3();
      S.raycaster.ray.intersectPlane(S.dragPlane, ix);
      S.dragOffset.copy(hit.position).sub(ix);
    } else {
      deselectFurniture();
    }
  });
  canvas.addEventListener('pointermove', (e) => {
    if (S.fpsMode) return;
    if (S.placeMode && S.placeGhost) { fn.updatePlaceGhost(e); return; }
    if (S.wallMode && S.wallStart) { fn.updateWallPreview(getGroundPoint(e)); return; }
    if (!S.dragTarget) return;
    S.mouse.x = (e.clientX / (innerWidth - SIDEBAR_W)) * 2 - 1;
    S.mouse.y = -(e.clientY / innerHeight) * 2 + 1;
    S.raycaster.setFromCamera(S.mouse, S.camera);
    const ix = new THREE.Vector3();
    S.raycaster.ray.intersectPlane(S.dragPlane, ix);
    const nx = fn.snapToGrid(ix.x + S.dragOffset.x);
    const nz = fn.snapToGrid(ix.z + S.dragOffset.z);
    const dx = nx - S.dragTarget.position.x;
    const dz = nz - S.dragTarget.position.z;
    if (dx === 0 && dz === 0) return;
    // move all selected
    const toMove = multiDragStarts ? [...multiDragStarts.keys()] : [S.dragTarget];
    for (const m of toMove) { m.position.x += dx; m.position.z += dz; }
    // collision check — if any collide, revert all
    let blocked = false;
    if (S.collisionEnabled) {
      const moveSet = new Set(toMove);
      for (const m of toMove) {
        if (fn.checkCollision(m, moveSet)) { blocked = true; break; }
      }
    }
    if (blocked) {
      for (const m of toMove) { m.position.x -= dx; m.position.z -= dz; }
    } else {
      S.dragLastValid = S.dragTarget.position.clone();
    }
    updatePosDisplay(S.dragTarget);
  });
  canvas.addEventListener('pointerup', () => {
    if (S.dragTarget && S.dragStartPos) {
      if (multiDragStarts && multiDragStarts.size > 0) {
        for (const [m, startPos] of multiDragStarts) {
          if (!m.position.equals(startPos)) {
            fn.pushUndo({ type: 'move', mesh: m, oldPos: startPos, newPos: m.position.clone() });
          }
        }
      } else if (!S.dragTarget.position.equals(S.dragStartPos)) {
        fn.pushUndo({ type: 'move', mesh: S.dragTarget, oldPos: S.dragStartPos, newPos: S.dragTarget.position.clone() });
      }
    }
    S.dragTarget = null; S.dragStartPos = null; S.dragLastValid = null; multiDragStarts = null;
    if (!S.fpsMode) S.orbit.enabled = true;
  });
}
function copySelected() {
  if (!S.selectedTarget) return;
  const m = S.selectedTarget;
  S.clipboard = {
    dims: getMeshDims(m), color: m.material?.color?.getHex() ?? 0x888888,
    furnitureType: m.userData.furnitureType || null, isWall: !!m.userData.isWall, rotation: m.rotation.y,
  };
}
function pasteClipboard() {
  if (!S.clipboard) return;
  const c = S.clipboard;
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(c.dims.w, c.dims.h, c.dims.d),
    new THREE.MeshLambertMaterial({ color: c.color })
  );
  mesh.position.set(fn.snapToGrid(S.orbit.target.x), c.dims.h / 2, fn.snapToGrid(S.orbit.target.z));
  mesh.rotation.y = c.rotation;
  mesh.castShadow = true; mesh.receiveShadow = true;
  mesh.userData = { draggable: true, baseY: c.dims.h / 2 };
  if (c.furnitureType) mesh.userData.furnitureType = c.furnitureType;
  if (c.isWall) { mesh.userData.isWall = true; S.userWalls.push(mesh); }
  S.scene.add(mesh); S.draggables.push(mesh);
  if (fn.checkCollision(mesh)) { S.scene.remove(mesh); rm(S.draggables, mesh); if (c.isWall) rm(S.userWalls, mesh); fn.showCollisionFlash(); return; }
  fn.pushUndo({ type: 'add', mesh, inUserWalls: c.isWall });
  selectFurniture(mesh); fn.refreshSceneList();
}
function rm(arr, item) { const i = arr.indexOf(item); if (i >= 0) arr.splice(i, 1); }
