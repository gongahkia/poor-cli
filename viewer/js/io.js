import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { S, fn } from './state.js';
import { FURNITURE } from './furniture.js';
const loader = new GLTFLoader();
export function initIO() {
  const glbParam = new URLSearchParams(location.search).get('glb');
  loader.load(glbParam || './model.glb', (gltf) => ingestGLB(gltf), undefined, () => {});
  document.getElementById('glb-input').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) loader.load(URL.createObjectURL(file), (gltf) => ingestGLB(gltf));
  });
  document.getElementById('export-glb-btn').addEventListener('click', exportGLB);
  document.getElementById('export-json-btn').addEventListener('click', exportJSON);
  document.getElementById('json-input').addEventListener('change', importJSON);
  startMcpSync();
}
function clearModelParts() {
  for (const m of S.modelParts) {
    S.scene.remove(m);
    const di = S.draggables.indexOf(m); if (di >= 0) S.draggables.splice(di, 1);
  }
  S.modelParts.length = 0;
}
function ingestGLB(gltf) {
  clearModelParts();
  const meshes = [];
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((child) => { if (child.isMesh) meshes.push(child); });
  const tempBox = new THREE.Box3();
  for (const mesh of meshes) {
    const m = mesh.clone();
    m.applyMatrix4(mesh.matrixWorld);
    m.castShadow = true; m.receiveShadow = true;
    m.userData.draggable = true; m.userData.isModelPart = true; m.userData.baseY = undefined;
    S.scene.add(m); S.draggables.push(m); S.modelParts.push(m);
  }
  if (S.modelParts.length > 0) {
    tempBox.makeEmpty();
    for (const m of S.modelParts) tempBox.expandByObject(m);
    const center = tempBox.getCenter(new THREE.Vector3());
    S.orbit.target.copy(center);
    S.camera.position.set(center.x + 10, center.y + 8, center.z + 10);
    S.orbit.update();
  }
  fn.refreshSceneList();
  if (fn.pushLayoutToServer) fn.pushLayoutToServer();
}
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
function exportGLB() {
  const exportScene = new THREE.Scene();
  for (const m of S.draggables) {
    if (!m.visible) continue;
    const clone = m.clone();
    const ol = clone.getObjectByName('_outline'); if (ol) clone.remove(ol);
    exportScene.add(clone);
  }
  const exporter = new GLTFExporter();
  exporter.parse(exportScene, (result) => {
    downloadBlob(new Blob([result], { type: 'application/octet-stream' }), 'haus-export.glb');
  }, (err) => { console.error('GLB export failed', err); }, { binary: true });
}
function serializeLayout() {
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
function exportJSON() {
  downloadBlob(new Blob([JSON.stringify(serializeLayout(), null, 2)], { type: 'application/json' }), 'haus-layout.json');
}
let lastMcpText = '';
let lastPushStamp = 0;
let lastPullStamp = 0;
function startMcpSync() {
  fn.pushLayoutToServer = pushLayoutToServer;
  pushLayoutToServer();
  setInterval(pushLayoutToServer, 3000);
  // pull changes made by MCP/chat — only if stamp differs from what we pushed
  setInterval(async () => {
    try {
      const res = await fetch('./mcp-layout.json?t=' + Date.now());
      if (!res.ok) return;
      const text = await res.text();
      if (text === lastMcpText) return;
      lastMcpText = text;
      const data = JSON.parse(text);
      if (!data.items) return;
      // skip if this was written by our own push
      if (data._stamp && data._stamp === lastPushStamp) return;
      if (data._stamp && data._stamp === lastPullStamp) return;
      lastPullStamp = data._stamp || 0;
      applyLayoutData(data);
    } catch {}
  }, 2000);
}
async function pushLayoutToServer() {
  try {
    const data = serializeLayout();
    const stamp = Date.now();
    data._stamp = stamp;
    lastPushStamp = stamp;
    await fetch('/api/sync-layout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  } catch {}
}
function applyLayoutData(data) {
  const prev = serializeLayout();
  clearModelParts();
  while (S.draggables.length) S.scene.remove(S.draggables.pop());
  S.userWalls.length = 0; S.redoStack.length = 0;
  fn.deselectFurniture();
  for (const item of data.items) {
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
  if (prev.items.length > 0) fn.pushUndo({ type: 'mcp_sync', snapshot: prev });
  fn.refreshSceneList();
}
function importJSON(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!data.items) return;
      clearModelParts();
      while (S.draggables.length) S.scene.remove(S.draggables.pop());
      S.userWalls.length = 0; S.undoStack.length = 0; S.redoStack.length = 0;
      fn.deselectFurniture();
      for (const item of data.items) {
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
      if (S.draggables.length > 0) {
        const box = new THREE.Box3(); box.makeEmpty();
        for (const m of S.draggables) box.expandByObject(m);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const dist = Math.max(size.x, size.y, size.z, 1) * 1.5;
        S.orbit.target.copy(center);
        S.camera.position.set(center.x + dist * 0.7, center.y + dist * 0.5, center.z + dist * 0.7);
        S.orbit.update();
      }
      fn.refreshSceneList();
    } catch (err) { console.error('JSON import failed', err); }
  };
  reader.readAsText(file);
  e.target.value = '';
}
