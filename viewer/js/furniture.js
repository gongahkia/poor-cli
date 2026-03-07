import * as THREE from 'three';
import { S, fn } from './state.js';
export const FURNITURE = {
  bed_single:      { w: 0.9,  h: 0.5,  d: 1.9, color: 0x88bbee },
  bed_queen:       { w: 1.5,  h: 0.55, d: 2.0, color: 0x77aadd },
  bed_king:        { w: 1.8,  h: 0.55, d: 2.0, color: 0x6699cc },
  wardrobe:        { w: 1.8,  h: 2.0,  d: 0.6, color: 0x4A3728 },
  wardrobe_s:      { w: 0.9,  h: 2.0,  d: 0.6, color: 0x5A4738 },
  bedside:         { w: 0.5,  h: 0.5,  d: 0.4, color: 0x8B7355 },
  dresser:         { w: 1.2,  h: 0.8,  d: 0.5, color: 0x7A6245 },
  sofa_2:          { w: 1.5,  h: 0.8,  d: 0.8, color: 0x555555 },
  sofa_3:          { w: 2.2,  h: 0.8,  d: 0.9, color: 0x4a4a4a },
  sofa_l:          { w: 2.2,  h: 0.8,  d: 1.6, color: 0x505050 },
  coffee:          { w: 1.0,  h: 0.4,  d: 0.5, color: 0x6B4226 },
  tv_console:      { w: 1.5,  h: 0.5,  d: 0.4, color: 0x3a3a3a },
  dining_4:        { w: 1.2,  h: 0.75, d: 0.8, color: 0x8B6914 },
  dining_6:        { w: 1.6,  h: 0.75, d: 0.9, color: 0x8B6914 },
  shoe_rack:       { w: 0.8,  h: 1.0,  d: 0.3, color: 0x5C4033 },
  fridge:          { w: 0.7,  h: 1.7,  d: 0.7, color: 0xcccccc },
  washer:          { w: 0.6,  h: 0.85, d: 0.6, color: 0xdddddd },
  kitchen_counter: { w: 1.2,  h: 0.9,  d: 0.6, color: 0x888888 },
  sink:            { w: 0.8,  h: 0.85, d: 0.6, color: 0x999999 },
  toilet:          { w: 0.4,  h: 0.4,  d: 0.7, color: 0xeeeeee },
  shower:          { w: 0.9,  h: 2.0,  d: 0.9, color: 0xaaddee },
  desk:            { w: 1.2,  h: 0.75, d: 0.6, color: 0xD2B48C },
  desk_l:          { w: 1.6,  h: 0.75, d: 1.2, color: 0xC4A882 },
  bookshelf:       { w: 0.8,  h: 1.8,  d: 0.3, color: 0x5A4020 },
  chair:           { w: 0.5,  h: 0.45, d: 0.5, color: 0x333333 },
};
export const FURNITURE_NAMES = {
  bed_single: 'Single Bed', bed_queen: 'Queen Bed', bed_king: 'King Bed',
  wardrobe: 'Wardrobe', wardrobe_s: 'Wardrobe S', bedside: 'Bedside Table', dresser: 'Dresser',
  sofa_2: '2-Seat Sofa', sofa_3: '3-Seat Sofa', sofa_l: 'L-Sofa',
  coffee: 'Coffee Table', tv_console: 'TV Console',
  dining_4: 'Dining 4', dining_6: 'Dining 6', shoe_rack: 'Shoe Rack',
  fridge: 'Fridge', washer: 'Washer', kitchen_counter: 'Counter',
  sink: 'Sink Cabinet', toilet: 'Toilet', shower: 'Shower',
  desk: 'Desk', desk_l: 'L-Desk', bookshelf: 'Bookshelf', chair: 'Office Chair',
};
export function initFurniture() {
  fn.enterPlaceMode = enterPlaceMode;
  fn.cancelPlaceMode = cancelPlaceMode;
  fn.confirmPlacement = confirmPlacement;
  fn.updatePlaceGhost = updatePlaceGhost;
  document.querySelectorAll('.furniture-btn').forEach(btn => {
    btn.addEventListener('click', () => enterPlaceMode(btn.dataset.type));
  });
}
function enterPlaceMode(type) {
  cancelPlaceMode();
  if (S.wallMode) fn.exitWallMode();
  fn.deselectFurniture();
  S.placeMode = true; S.placeType = type;
  const f = FURNITURE[type];
  const geo = new THREE.BoxGeometry(f.w, f.h, f.d);
  const mat = new THREE.MeshLambertMaterial({ color: f.color, transparent: true, opacity: 0.45 });
  S.placeGhost = new THREE.Mesh(geo, mat);
  S.placeGhost.position.set(0, f.h / 2, 0);
  const edges = new THREE.EdgesGeometry(geo);
  const ol = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x44ddaa, linewidth: 2 }));
  ol.name = '_ghost_outline';
  S.placeGhost.add(ol);
  S.scene.add(S.placeGhost);
  S.renderer.domElement.style.cursor = 'crosshair';
}
function cancelPlaceMode() {
  if (S.placeGhost) { S.scene.remove(S.placeGhost); S.placeGhost.geometry.dispose(); S.placeGhost.material.dispose(); S.placeGhost = null; }
  S.placeMode = false; S.placeType = null; S.placeBlocked = false;
  S.renderer.domElement.style.cursor = '';
}
function confirmPlacement() {
  if (!S.placeGhost || S.placeBlocked) { if (S.placeBlocked) fn.showCollisionFlash(); return; }
  const f = FURNITURE[S.placeType];
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(f.w, f.h, f.d), new THREE.MeshLambertMaterial({ color: f.color }));
  mesh.castShadow = true; mesh.receiveShadow = true;
  mesh.position.copy(S.placeGhost.position);
  mesh.userData = { draggable: true, baseY: f.h / 2, furnitureType: S.placeType };
  S.scene.add(mesh); S.draggables.push(mesh);
  fn.pushUndo({ type: 'add', mesh, inUserWalls: false });
  cancelPlaceMode();
  fn.selectFurniture(mesh);
}
function updatePlaceGhost(e) {
  const pt = fn.getGroundPoint(e);
  const f = FURNITURE[S.placeType];
  S.placeGhost.position.set(pt.x, f.h / 2, pt.z);
  S.placeBlocked = S.collisionEnabled && fn.checkCollision(S.placeGhost);
  const ol = S.placeGhost.getObjectByName('_ghost_outline');
  if (ol) ol.material.color.setHex(S.placeBlocked ? 0xdd4444 : 0x44ddaa);
  S.placeGhost.material.color.setHex(S.placeBlocked ? 0xdd4444 : f.color);
}
