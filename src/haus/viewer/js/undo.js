import * as THREE from 'three';
import { S, fn, MAX_UNDO } from './state.js';
export function initUndo() {
  fn.pushUndo = pushUndo;
  fn.undo = undo;
  fn.redo = redo;
}
function pushUndo(action) {
  S.undoStack.push(action);
  if (S.undoStack.length > MAX_UNDO) S.undoStack.shift();
  S.redoStack.length = 0;
}
function undo() {
  if (S.undoStack.length === 0) return;
  const a = S.undoStack.pop();
  applyReverse(a);
  S.redoStack.push(a);
  fn.refreshSceneList();
}
function redo() {
  if (S.redoStack.length === 0) return;
  const a = S.redoStack.pop();
  applyForward(a);
  S.undoStack.push(a);
  fn.refreshSceneList();
}
function rm(arr, item) { const i = arr.indexOf(item); if (i >= 0) arr.splice(i, 1); }
function rebuildFromSnapshot(snapshot) {
  fn.deselectFurniture();
  while (S.draggables.length) S.scene.remove(S.draggables.pop());
  S.userWalls.length = 0; S.modelParts.length = 0;
  for (const item of snapshot.items) {
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(item.geo[0], item.geo[1], item.geo[2]),
      new THREE.MeshLambertMaterial({ color: item.color })
    );
    mesh.position.set(item.pos[0], item.pos[1], item.pos[2]);
    mesh.rotation.y = item.rot;
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.userData.draggable = true; mesh.visible = item.visible !== false;
    if (item.type === 'wall') { mesh.userData.isWall = true; mesh.userData.baseY = item.geo[1] / 2; S.userWalls.push(mesh); }
    else if (item.type === 'model_part') { mesh.userData.isModelPart = true; S.modelParts.push(mesh); }
    else { mesh.userData.baseY = item.geo[1] / 2; if (item.furnitureType) mesh.userData.furnitureType = item.furnitureType; }
    if (item.name) mesh.userData.name = item.name;
    if (item.room) mesh.userData.room = item.room;
    S.scene.add(mesh); S.draggables.push(mesh);
  }
}
function serializeForUndo() {
  const items = [];
  for (const m of S.draggables) {
    const entry = { pos: [m.position.x, m.position.y, m.position.z], rot: m.rotation.y, visible: m.visible };
    if (m.userData.isWall) {
      entry.type = 'wall';
      entry.geo = [m.geometry.parameters.width, m.geometry.parameters.height, m.geometry.parameters.depth];
      entry.color = m.material.color.getHex();
    } else if (m.userData.isModelPart) {
      entry.type = 'model_part';
      const size = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
      entry.geo = [size.x, size.y, size.z];
      entry.color = m.material?.color?.getHex() ?? 0x888888;
    } else {
      entry.type = 'furniture';
      entry.furnitureType = m.userData.furnitureType || null;
      entry.geo = [m.geometry.parameters.width, m.geometry.parameters.height, m.geometry.parameters.depth];
      entry.color = m.material.color.getHex();
    }
    if (m.userData.name) entry.name = m.userData.name;
    if (m.userData.room) entry.room = m.userData.room;
    items.push(entry);
  }
  return { version: 1, items };
}
function applyReverse(a) {
  if (a.type === 'mcp_sync') {
    a.forwardSnapshot = serializeForUndo();
    rebuildFromSnapshot(a.snapshot);
    return;
  }
  if (a.type === 'add') {
    S.scene.remove(a.mesh);
    rm(S.draggables, a.mesh); rm(S.userWalls, a.mesh);
    if (S.selectedTarget === a.mesh) fn.deselectFurniture();
  } else if (a.type === 'delete') {
    S.scene.add(a.mesh);
    S.draggables.push(a.mesh);
    if (a.inUserWalls) S.userWalls.push(a.mesh);
    if (a.inModelParts) S.modelParts.push(a.mesh);
  } else if (a.type === 'move') {
    a.mesh.position.copy(a.oldPos);
  } else if (a.type === 'rotate') {
    a.mesh.rotation.y = a.oldRot;
  } else if (a.type === 'resize') {
    a.mesh.geometry.dispose();
    a.mesh.geometry = new THREE.BoxGeometry(a.oldDims.w, a.oldDims.h, a.oldDims.d);
    a.mesh.position.y = a.oldY; a.mesh.userData.baseY = a.oldY;
    if (a.mesh === S.selectedTarget) { fn.populateDimSliders(a.mesh); fn.refreshOutline(a.mesh); }
  } else if (a.type === 'color') {
    a.mesh.material.color.setHex(a.oldColor);
  }
}
function applyForward(a) {
  if (a.type === 'mcp_sync') {
    rebuildFromSnapshot(a.forwardSnapshot);
    return;
  }
  if (a.type === 'add') {
    S.scene.add(a.mesh);
    S.draggables.push(a.mesh);
    if (a.inUserWalls) S.userWalls.push(a.mesh);
  } else if (a.type === 'delete') {
    S.scene.remove(a.mesh);
    rm(S.draggables, a.mesh); rm(S.userWalls, a.mesh); rm(S.modelParts, a.mesh);
    if (S.selectedTarget === a.mesh) fn.deselectFurniture();
  } else if (a.type === 'move') {
    a.mesh.position.copy(a.newPos);
  } else if (a.type === 'rotate') {
    a.mesh.rotation.y = a.newRot;
  } else if (a.type === 'resize') {
    a.mesh.geometry.dispose();
    a.mesh.geometry = new THREE.BoxGeometry(a.newDims.w, a.newDims.h, a.newDims.d);
    a.mesh.position.y = a.newY; a.mesh.userData.baseY = a.newY;
    if (a.mesh === S.selectedTarget) { fn.populateDimSliders(a.mesh); fn.refreshOutline(a.mesh); }
  } else if (a.type === 'color') {
    a.mesh.material.color.setHex(a.newColor);
  }
}
