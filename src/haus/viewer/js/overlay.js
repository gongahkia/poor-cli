import * as THREE from 'three';
import { S, fn } from './state.js';
let overlayMesh = null;
let overlayScale = 1.0;
let overlayOpacity = 0.5;
export function initOverlay() {
  document.getElementById('overlay-input').addEventListener('change', loadOverlay);
  document.getElementById('overlay-clear').addEventListener('click', clearOverlay);
  const scaleSlider = document.getElementById('overlay-scale');
  const scaleLabel = document.getElementById('overlay-scale-label');
  scaleSlider.addEventListener('input', () => {
    overlayScale = parseInt(scaleSlider.value) / 100;
    scaleLabel.textContent = overlayScale.toFixed(2) + 'x';
    if (overlayMesh) { overlayMesh.scale.set(overlayScale, 1, overlayScale); }
  });
  const opacSlider = document.getElementById('overlay-opacity');
  const opacLabel = document.getElementById('overlay-opacity-label');
  opacSlider.addEventListener('input', () => {
    overlayOpacity = parseInt(opacSlider.value) / 100;
    opacLabel.textContent = Math.round(overlayOpacity * 100) + '%';
    if (overlayMesh) overlayMesh.material.opacity = overlayOpacity;
  });
}
function loadOverlay(e) {
  const file = e.target.files[0];
  if (!file) return;
  clearOverlay();
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    const aspect = img.width / img.height;
    const size = 20; // base size in meters
    const tex = new THREE.TextureLoader().load(url);
    tex.colorSpace = THREE.SRGBColorSpace;
    const geo = new THREE.PlaneGeometry(size * aspect, size);
    const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: overlayOpacity, side: THREE.DoubleSide });
    overlayMesh = new THREE.Mesh(geo, mat);
    overlayMesh.rotation.x = -Math.PI / 2;
    overlayMesh.position.y = 0.01; // slightly above ground
    overlayMesh.scale.set(overlayScale, 1, overlayScale);
    S.scene.add(overlayMesh);
    document.getElementById('overlay-controls').style.display = '';
  };
  img.src = url;
}
function clearOverlay() {
  if (overlayMesh) {
    S.scene.remove(overlayMesh);
    overlayMesh.geometry.dispose(); overlayMesh.material.map?.dispose(); overlayMesh.material.dispose();
    overlayMesh = null;
  }
  document.getElementById('overlay-controls').style.display = 'none';
}
