import * as THREE from 'three';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { S, fn } from './state.js';
let plControls = null;
const moveState = { forward: false, backward: false, left: false, right: false };
const EYE_HEIGHT = 1.6;
const WALK_SPEED = 4.0;
const RUN_SPEED = 8.0;
let prevTime = 0;
let running = false;
export function initCamera() {
  fn.frameScene = frameScene;
  fn.frameSelected = frameSelected;
  fn.setCameraView = setCameraView;
  fn.toggleOrtho = toggleOrtho;
  fn.toggleFps = toggleFps;
  fn.exitFps = exitFps;
  fn.captureScreenshot = captureScreenshot;
  plControls = new PointerLockControls(S.camera, S.renderer.domElement);
  plControls.addEventListener('lock', () => {
    S.orbit.enabled = false;
    document.getElementById('fps-crosshair').style.display = '';
    document.getElementById('fps-hint').style.display = '';
  });
  plControls.addEventListener('unlock', () => { if (S.fpsMode) exitFps(); });
  window.addEventListener('keydown', onFpsKeyDown);
  window.addEventListener('keyup', onFpsKeyUp);
  document.getElementById('fps-btn').addEventListener('click', toggleFps);
  document.getElementById('screenshot-btn').addEventListener('click', captureScreenshot);
}
function frameBounds(box) {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  return { center, size, dist: Math.max(size.x, size.y, size.z, 1) * 1.5 };
}
function frameScene() {
  const box = new THREE.Box3();
  const visible = S.draggables.filter((m) => m.visible);
  if (visible.length > 0) {
    box.makeEmpty();
    for (const m of visible) box.expandByObject(m);
  } else {
    box.setFromCenterAndSize(new THREE.Vector3(0, 0.8, 0), new THREE.Vector3(4.5, 2.6, 3.6));
  }

  const { center, size } = frameBounds(box);
  const footprint = Math.max(size.x, size.z, 3.5);
  const height = Math.max(size.y, 2.6);
  const dist = Math.max(footprint * 1.85, height * 3.2, 7.5);
  const target = center.clone();
  target.y = Math.max(0.75, Math.min(center.y + height * 0.16, 1.4));

  S.orbit.target.copy(target);
  S.camera.position.set(
    target.x + dist * 0.72,
    target.y + dist * 0.54,
    target.z + dist * 0.82,
  );
  if (S.camera.fov !== 45) {
    S.camera.fov = 45;
    S.camera.updateProjectionMatrix();
  }
  S.orbit.update();
}
function frameSelected() {
  const box = new THREE.Box3();
  if (S.selectedTarget) { box.setFromObject(S.selectedTarget); }
  else if (S.draggables.length > 0) { box.makeEmpty(); for (const m of S.draggables) if (m.visible) box.expandByObject(m); }
  else return;
  const { center, dist } = frameBounds(box);
  const dir = S.camera.position.clone().sub(S.orbit.target).normalize();
  S.orbit.target.copy(center);
  S.camera.position.copy(center).addScaledVector(dir, dist);
  S.orbit.update();
}
function setCameraView(direction) {
  const box = new THREE.Box3();
  if (S.draggables.length > 0) { box.makeEmpty(); for (const m of S.draggables) if (m.visible) box.expandByObject(m); }
  const { center, dist } = frameBounds(box);
  S.orbit.target.copy(center);
  if (direction === 'front') S.camera.position.set(center.x, center.y, center.z + dist);
  else if (direction === 'right') S.camera.position.set(center.x + dist, center.y, center.z);
  else if (direction === 'top') S.camera.position.set(center.x, center.y + dist, center.z + 0.001);
  S.orbit.update();
}
function toggleOrtho() {
  if (S.camera.fov === 1) { S.camera.fov = 50; }
  else {
    S.camera.fov = 1;
    const dir = S.camera.position.clone().sub(S.orbit.target).normalize();
    const d = S.camera.position.distanceTo(S.orbit.target);
    S.camera.position.copy(S.orbit.target).addScaledVector(dir, d * 50);
  }
  S.camera.updateProjectionMatrix();
}
function toggleFps() {
  if (S.fpsMode) { exitFps(); return; }
  if (S.wallMode) fn.exitWallMode();
  if (S.placeMode) fn.cancelPlaceMode();
  fn.deselectFurniture();
  S.fpsMode = true;
  const target = S.orbit.target.clone();
  S.camera.position.set(target.x, EYE_HEIGHT, target.z);
  S.camera.lookAt(target.x + 1, EYE_HEIGHT, target.z);
  if (S.camera.fov !== 50) { S.camera.fov = 50; S.camera.updateProjectionMatrix(); }
  prevTime = performance.now();
  plControls.lock();
  document.getElementById('fps-btn').classList.add('active');
}
function exitFps() {
  S.fpsMode = false;
  plControls.unlock();
  S.orbit.enabled = true;
  const dir = new THREE.Vector3();
  S.camera.getWorldDirection(dir);
  S.orbit.target.copy(S.camera.position).addScaledVector(dir, 5);
  S.orbit.update();
  document.getElementById('fps-crosshair').style.display = 'none';
  document.getElementById('fps-hint').style.display = 'none';
  document.getElementById('fps-btn').classList.remove('active');
  for (const k in moveState) moveState[k] = false;
  running = false;
}
function onFpsKeyDown(e) {
  if (!S.fpsMode) return;
  switch (e.code) {
    case 'KeyW': case 'ArrowUp': moveState.forward = true; break;
    case 'KeyA': case 'ArrowLeft': moveState.left = true; break;
    case 'KeyS': case 'ArrowDown': moveState.backward = true; break;
    case 'KeyD': case 'ArrowRight': moveState.right = true; break;
    case 'ShiftLeft': case 'ShiftRight': running = true; break;
  }
}
function onFpsKeyUp(e) {
  if (!S.fpsMode) return;
  switch (e.code) {
    case 'KeyW': case 'ArrowUp': moveState.forward = false; break;
    case 'KeyA': case 'ArrowLeft': moveState.left = false; break;
    case 'KeyS': case 'ArrowDown': moveState.backward = false; break;
    case 'KeyD': case 'ArrowRight': moveState.right = false; break;
    case 'ShiftLeft': case 'ShiftRight': running = false; break;
  }
}
export function updateFps() {
  if (!S.fpsMode || !plControls.isLocked) return;
  const now = performance.now();
  const delta = Math.min((now - prevTime) / 1000, 0.1); // clamp to avoid teleport on first frame
  prevTime = now;
  let fwd = Number(moveState.forward) - Number(moveState.backward);
  let right = Number(moveState.right) - Number(moveState.left);
  const len = Math.sqrt(fwd * fwd + right * right);
  if (len > 0) { fwd /= len; right /= len; } // normalize diagonal
  const speed = (running ? RUN_SPEED : WALK_SPEED) * delta;
  if (fwd !== 0) plControls.moveForward(fwd * speed);
  if (right !== 0) plControls.moveRight(right * speed);
  S.camera.position.y = EYE_HEIGHT; // locked to floor
}
function captureScreenshot() {
  S.renderer.render(S.scene, S.camera);
  const url = S.renderer.domElement.toDataURL('image/png');
  const a = document.createElement('a');
  a.href = url; a.download = 'haus-screenshot.png'; a.click();
  const flash = document.getElementById('screenshot-flash');
  flash.style.opacity = '1';
  setTimeout(() => { flash.style.opacity = '0'; }, 150);
}
