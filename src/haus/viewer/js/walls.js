import * as THREE from 'three';
import { S, fn, WALL_COLOR } from './state.js';
import { createSceneMaterial, prepareMeshForScene } from './scene.js';
export function initWalls() {
  fn.enterWallMode = enterWallMode;
  fn.exitWallMode = exitWallMode;
  fn.placeWall = placeWall;
  fn.updateWallPreview = updateWallPreview;
  document.getElementById('wall-btn').addEventListener('click', () => { if (S.wallMode) exitWallMode(); else enterWallMode(); });
  document.getElementById('wall-cancel-btn').addEventListener('click', exitWallMode);
  const hSlider = document.getElementById('wall-height-slider');
  const hLabel = document.getElementById('wall-height-label');
  hSlider.addEventListener('input', () => { S.wallHeight = parseInt(hSlider.value) / 10; hLabel.textContent = S.wallHeight.toFixed(1) + 'm'; });
  const tSlider = document.getElementById('wall-thick-slider');
  const tLabel = document.getElementById('wall-thick-label');
  tSlider.addEventListener('input', () => { S.wallThickness = parseInt(tSlider.value) * 0.05; tLabel.textContent = S.wallThickness.toFixed(2) + 'm'; });
}
function enterWallMode() {
  S.wallMode = true; S.wallStart = null;
  fn.deselectFurniture();
  document.getElementById('wall-btn').classList.add('active');
  document.getElementById('wall-cancel-btn').style.display = '';
  document.getElementById('wall-status').style.display = '';
  document.getElementById('wall-status').textContent = 'Click to place wall start point...';
  S.renderer.domElement.style.cursor = 'crosshair';
}
function exitWallMode() {
  S.wallMode = false; S.wallStart = null;
  if (S.wallPreview) { S.scene.remove(S.wallPreview); S.wallPreview = null; }
  document.getElementById('wall-btn').classList.remove('active');
  document.getElementById('wall-cancel-btn').style.display = 'none';
  document.getElementById('wall-status').style.display = 'none';
  S.renderer.domElement.style.cursor = '';
}
function buildWallMesh(p1, p2, thickness, height) {
  const dx = p2.x - p1.x, dz = p2.z - p1.z;
  const length = Math.sqrt(dx * dx + dz * dz);
  if (length < 0.01) return null;
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(length, height, thickness),
    createSceneMaterial('wall', WALL_COLOR)
  );
  mesh.position.set((p1.x + p2.x) / 2, height / 2, (p1.z + p2.z) / 2);
  mesh.rotation.y = -Math.atan2(dz, dx);
  return prepareMeshForScene(mesh, 'wall', WALL_COLOR, { replaceMaterial: false });
}
function updateWallPreview(endPt) {
  if (S.wallPreview) S.scene.remove(S.wallPreview);
  if (!S.wallStart) return;
  const mesh = buildWallMesh(S.wallStart, endPt, S.wallThickness, S.wallHeight);
  if (!mesh) return;
  S.scene.add(mesh);
  const blocked = S.collisionEnabled && fn.checkCollision(mesh);
  mesh.material = createSceneMaterial('ghost', blocked ? 0xdd4444 : 0x44ddaa, { opacity: 0.5 });
  S.wallPreview = mesh;
}
function placeWall(endPt) {
  const mesh = buildWallMesh(S.wallStart, endPt, S.wallThickness, S.wallHeight);
  if (!mesh) return;
  mesh.userData = { draggable: true, isWall: true, baseY: S.wallHeight / 2 };
  S.scene.add(mesh);
  if (fn.checkCollision(mesh)) { S.scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose(); fn.showCollisionFlash(); return; }
  S.draggables.push(mesh); S.userWalls.push(mesh);
  fn.pushUndo({ type: 'add', mesh, inUserWalls: true });
  fn.refreshSceneList();
}
