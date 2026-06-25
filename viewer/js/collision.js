import * as THREE from 'three';
import { S, fn } from './state.js';
const _box = new THREE.Box3();
let _timer = 0;
export function initCollision() {
  fn.checkCollision = checkCollision;
  fn.showCollisionFlash = showCollisionFlash;
  document.getElementById('collision-toggle').addEventListener('change', (e) => { S.collisionEnabled = e.target.checked; });
}
function checkCollision(mesh, exclude) {
  if (!S.collisionEnabled) return false;
  const box = new THREE.Box3().setFromObject(mesh);
  box.min.addScalar(0.005); box.max.addScalar(-0.005);
  for (const other of S.draggables) {
    if (other === mesh || !other.visible) continue;
    if (exclude && exclude.has(other)) continue;
    _box.setFromObject(other);
    _box.min.addScalar(0.005); _box.max.addScalar(-0.005);
    if (box.intersectsBox(_box)) return true;
  }
  return false;
}
function showCollisionFlash() {
  const el = document.getElementById('collision-flash');
  el.style.opacity = '1';
  clearTimeout(_timer);
  _timer = setTimeout(() => { el.style.opacity = '0'; }, 800);
}
