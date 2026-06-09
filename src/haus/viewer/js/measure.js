import * as THREE from 'three';
import { S, fn, sceneViewportWidth } from './state.js';
const lineMat = new THREE.LineBasicMaterial({ color: 0xa78bfa, linewidth: 2, depthTest: false });
const dotGeo = new THREE.SphereGeometry(0.06, 8, 8);
const dotMat = new THREE.MeshBasicMaterial({ color: 0xa78bfa, depthTest: false });
let labelEl = null;
let dots = [];
export function initMeasure() {
  fn.toggleMeasure = toggleMeasure;
  fn.exitMeasure = exitMeasure;
  fn.measureClick = measureClick;
  labelEl = document.createElement('div');
  labelEl.id = 'measure-label';
  labelEl.style.cssText = 'position:fixed;z-index:60;font-size:13px;font-weight:600;color:#a78bfa;background:rgba(15,15,15,0.72);padding:2px 8px;border-radius:4px;pointer-events:none;display:none;';
  document.body.appendChild(labelEl);
  document.getElementById('measure-btn').addEventListener('click', toggleMeasure);
}
function toggleMeasure() {
  if (S.measureMode) exitMeasure();
  else enterMeasure();
}
function enterMeasure() {
  if (S.wallMode) fn.exitWallMode();
  if (S.placeMode) fn.cancelPlaceMode();
  if (S.fpsMode) fn.exitFps();
  fn.deselectFurniture();
  S.measureMode = true;
  S.measureStart = null;
  clearVisuals();
  document.getElementById('measure-btn').classList.add('active');
  S.renderer.domElement.style.cursor = 'crosshair';
}
function exitMeasure() {
  S.measureMode = false;
  S.measureStart = null;
  document.getElementById('measure-btn').classList.remove('active');
  S.renderer.domElement.style.cursor = '';
}
function clearVisuals() {
  if (S.measureLine) { S.scene.remove(S.measureLine); S.measureLine = null; }
  for (const d of dots) S.scene.remove(d);
  dots = [];
  labelEl.style.display = 'none';
}
function addDot(pt) {
  const d = new THREE.Mesh(dotGeo, dotMat);
  d.position.copy(pt); d.position.y = 0.05;
  d.renderOrder = 999;
  S.scene.add(d); dots.push(d);
}
function measureClick(e) {
  const mouse = new THREE.Vector2(
    (e.clientX / sceneViewportWidth()) * 2 - 1,
    -(e.clientY / innerHeight) * 2 + 1
  );
  S.raycaster.setFromCamera(mouse, S.camera);
  const pt = new THREE.Vector3();
  S.raycaster.ray.intersectPlane(S.dragPlane, pt);
  pt.x = fn.snapToGrid(pt.x); pt.z = fn.snapToGrid(pt.z); pt.y = 0;
  if (!S.measureStart) {
    clearVisuals();
    S.measureStart = pt.clone();
    addDot(pt);
    return;
  }
  // second click — draw line + label
  const start = S.measureStart;
  const end = pt;
  const dx = end.x - start.x, dz = end.z - start.z;
  const dist = Math.sqrt(dx * dx + dz * dz);
  addDot(end);
  // line
  const geo = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(start.x, 0.05, start.z),
    new THREE.Vector3(end.x, 0.05, end.z),
  ]);
  S.measureLine = new THREE.Line(geo, lineMat);
  S.measureLine.renderOrder = 999;
  S.scene.add(S.measureLine);
  // position label at midpoint in screen space
  const mid = new THREE.Vector3((start.x + end.x) / 2, 0.3, (start.z + end.z) / 2);
  const screen = mid.project(S.camera);
  const hw = sceneViewportWidth() / 2, hh = innerHeight / 2;
  labelEl.textContent = dist.toFixed(3) + 'm';
  labelEl.style.left = (screen.x * hw + hw) + 'px';
  labelEl.style.top = (-screen.y * hh + hh) + 'px';
  labelEl.style.display = '';
  S.measureStart = null; // ready for next measurement
}
