import * as THREE from 'three';
import { S, fn } from './state.js';
export function initGrid() {
  S.gridGroup = new THREE.Group();
  S.scene.add(S.gridGroup);
  fn.snapToGrid = snapToGrid;
  fn.rebuildGrid = rebuildGrid;
  rebuildGrid();
  document.getElementById('grid-toggle').addEventListener('change', (e) => { S.gridGroup.visible = e.target.checked; });
  document.getElementById('snap-toggle').addEventListener('change', (e) => { S.snapEnabled = e.target.checked; });
  const slider = document.getElementById('snap-size');
  const label = document.getElementById('snap-val-label');
  const update = () => {
    S.gridDivisions = parseInt(slider.value);
    label.textContent = (1.0 / S.gridDivisions).toFixed(2) + 'm';
    rebuildGrid();
  };
  slider.addEventListener('input', update);
  update();
}
function rebuildGrid() {
  S.gridGroup.clear();
  const extent = 50;
  const major = new THREE.GridHelper(extent, extent, 0x555555, 0x555555);
  major.material.transparent = true; major.material.opacity = 0.5;
  S.gridGroup.add(major);
  if (S.gridDivisions > 1) {
    const totalDivs = Math.floor(extent / (1.0 / S.gridDivisions));
    const minor = new THREE.GridHelper(extent, totalDivs, 0x333333, 0x333333);
    minor.material.transparent = true; minor.material.opacity = 0.25;
    minor.position.y = -0.001;
    S.gridGroup.add(minor);
  }
}
function snapToGrid(val) {
  if (!S.snapEnabled) return val;
  const c = 1.0 / S.gridDivisions;
  return Math.round(val / c) * c;
}
