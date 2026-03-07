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
function applyReverse(a) {
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
