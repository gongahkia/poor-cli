import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { S, fn } from './state.js';
import { FURNITURE } from './furniture.js';
import { createSceneMaterial, prepareMeshForScene } from './scene.js';
const loader = new GLTFLoader();
export function initIO() {
  const glbParam = new URLSearchParams(location.search).get('glb');
  loader.load(
    glbParam || './model.glb',
    (gltf) => ingestGLB(gltf),
    undefined,
    (err) => {
      if (glbParam) {
        console.error('Failed loading GLB from query param', err);
      } else {
        console.warn('No default model.glb found yet. You can still place furniture manually.');
      }
    },
  );
  document.getElementById('glb-input').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      loader.load(
        URL.createObjectURL(file),
        (gltf) => ingestGLB(gltf),
        undefined,
        (err) => console.error('Failed loading uploaded GLB', err),
      );
    }
  });
  document.getElementById('export-glb-btn').addEventListener('click', exportGLB);
  document.getElementById('export-json-btn').addEventListener('click', exportJSON);
  document.getElementById('json-input').addEventListener('change', importJSON);
  fn.clearLayoutAndSync = clearLayoutAndSync;
  fn.applyLayoutData = applyLayoutData;
  startMcpSync();
}
function clearModelParts() {
  for (const m of S.modelParts) {
    S.scene.remove(m);
    const di = S.draggables.indexOf(m); if (di >= 0) S.draggables.splice(di, 1);
  }
  S.modelParts.length = 0;
}
function materialKindForItem(item) {
  if (item.type === 'wall') return 'wall';
  if (item.type === 'model_part') return 'model';
  return 'furniture';
}
function buildMeshFromLayoutItem(item) {
  if (!item.geo || !item.pos || item.geo.length < 3 || item.pos.length < 3) {
    console.warn('Skipping malformed layout item', item);
    return null;
  }

  const kind = materialKindForItem(item);
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(item.geo[0], item.geo[1], item.geo[2]),
    createSceneMaterial(kind, item.color)
  );
  prepareMeshForScene(mesh, kind, item.color, { replaceMaterial: false });
  mesh.position.set(item.pos[0], item.pos[1], item.pos[2]);
  mesh.rotation.y = item.rot;
  mesh.userData.draggable = true;
  mesh.visible = item.visible !== false;

  if (item.type === 'wall') {
    mesh.userData.isWall = true;
    mesh.userData.baseY = item.geo[1] / 2;
    S.userWalls.push(mesh);
  } else if (item.type === 'model_part') {
    mesh.userData.isModelPart = true;
    S.modelParts.push(mesh);
  } else {
    mesh.userData.baseY = item.geo[1] / 2;
    if (item.furnitureType) mesh.userData.furnitureType = item.furnitureType;
  }
  if (item.name) mesh.userData.name = item.name;
  if (item.room) mesh.userData.room = item.room;
  return mesh;
}
function ingestGLB(gltf) {
  clearModelParts();
  const meshes = [];
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((child) => { if (child.isMesh) meshes.push(child); });
  for (const mesh of meshes) {
    const m = mesh.clone();
    m.applyMatrix4(mesh.matrixWorld);
    const color = m.material?.color?.getHex?.() ?? 0xb8b8b8;
    prepareMeshForScene(m, 'model', color);
    m.userData.draggable = true; m.userData.isModelPart = true; m.userData.baseY = undefined;
    S.scene.add(m); S.draggables.push(m); S.modelParts.push(m);
  }
  if (S.modelParts.length > 0 && fn.frameScene) fn.frameScene();
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
    const cs = clone.getObjectByName('_contact_shadow'); if (cs) clone.remove(cs);
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
  const layout = { version: 1, items };
  if (S.layoutMetadata) layout.metadata = S.layoutMetadata;
  if (Array.isArray(S.layoutRooms) && S.layoutRooms.length > 0) layout.rooms = S.layoutRooms;
  return layout;
}
function exportJSON() {
  downloadBlob(new Blob([JSON.stringify(serializeLayout(), null, 2)], { type: 'application/json' }), 'haus-layout.json');
}
let lastMcpText = '';
let lastPushStamp = 0;
let lastPullStamp = 0;
let pullFailureCount = 0;
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
      applyLayoutData(data, { frame: false });
      pullFailureCount = 0;
    } catch (err) {
      pullFailureCount += 1;
      if (pullFailureCount <= 3 || pullFailureCount % 10 === 0) {
        console.warn('MCP layout pull failed', err);
      }
    }
  }, 2000);
}
async function pushLayoutToServer() {
  try {
    const data = serializeLayout();
    const stamp = Date.now();
    data._stamp = stamp;
    lastPushStamp = stamp;
    await pushLayoutPayload(data);
  } catch (err) {
    console.warn('MCP layout push failed', err);
  }
}
async function pushLayoutPayload(data) {
  const res = await fetch('/api/sync-layout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`sync failed with HTTP ${res.status}`);
  }
}
function clearLocalLayout({ recordUndo = true } = {}) {
  const snapshot = serializeLayout();
  if (recordUndo && snapshot.items.length > 0) {
    fn.pushUndo({ type: 'mcp_sync', snapshot });
  }

  fn.deselectFurniture();
  if (fn.clearSightlineOverlay) fn.clearSightlineOverlay();
  clearModelParts();
  while (S.draggables.length) S.scene.remove(S.draggables.pop());
  S.userWalls.length = 0;
  S.hiddenObjects.length = 0;
  S.layoutMetadata = null;
  S.layoutRooms = [];
  S.redoStack.length = 0;
  fn.refreshSceneList();

  return snapshot;
}
async function clearLayoutAndSync({ confirmWithMcp = true } = {}) {
  const snapshot = clearLocalLayout({ recordUndo: true });

  const payload = { version: 1, items: [] };
  const stamp = Date.now();
  payload._stamp = stamp;
  lastPushStamp = stamp;

  try {
    await pushLayoutPayload(payload);
  } catch (err) {
    console.warn('Clear layout sync failed, restoring previous local scene', err);
    applyLayoutData(snapshot, { recordUndo: false, frame: false });
    return { ok: false, error: err.message || String(err) };
  }

  if (!confirmWithMcp) {
    return { ok: true, mcp: { ok: true, skipped: true } };
  }

  try {
    const res = await fetch('/api/mcp/clear-layout', { method: 'POST' });
    if (!res.ok) {
      return { ok: true, mcp: { ok: false, error: `HTTP ${res.status}` } };
    }
    const body = await res.json();
    return { ok: true, mcp: { ok: body.ok !== false, result: body.result || '' } };
  } catch (err) {
    return { ok: true, mcp: { ok: false, error: err.message || String(err) } };
  }
}
function applyLayoutData(data, { recordUndo = true, frame = true } = {}) {
  if (!Array.isArray(data.items)) {
    console.warn('Ignoring malformed MCP layout payload: items missing array');
    return;
  }
  const prev = serializeLayout();
  S.layoutMetadata = data.metadata && typeof data.metadata === 'object' ? data.metadata : null;
  S.layoutRooms = Array.isArray(data.rooms) ? data.rooms : [];
  clearModelParts();
  while (S.draggables.length) S.scene.remove(S.draggables.pop());
  S.userWalls.length = 0; S.redoStack.length = 0;
  fn.deselectFurniture();
  if (fn.clearSightlineOverlay) fn.clearSightlineOverlay();
  for (const item of data.items) {
    const mesh = buildMeshFromLayoutItem(item);
    if (!mesh) continue;
    S.scene.add(mesh); S.draggables.push(mesh);
  }
  if (recordUndo && prev.items.length > 0) fn.pushUndo({ type: 'mcp_sync', snapshot: prev });
  if (frame && S.draggables.length > 0 && fn.frameScene) fn.frameScene();
  fn.refreshSceneList();
}
function importJSON(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!Array.isArray(data.items)) {
        console.warn('JSON import missing items array');
        return;
      }
      S.layoutMetadata = data.metadata && typeof data.metadata === 'object' ? data.metadata : null;
      S.layoutRooms = Array.isArray(data.rooms) ? data.rooms : [];
      clearModelParts();
      while (S.draggables.length) S.scene.remove(S.draggables.pop());
      S.userWalls.length = 0; S.undoStack.length = 0; S.redoStack.length = 0;
      fn.deselectFurniture();
      if (fn.clearSightlineOverlay) fn.clearSightlineOverlay();
      for (const item of data.items) {
        const mesh = buildMeshFromLayoutItem(item);
        if (!mesh) continue;
        S.scene.add(mesh); S.draggables.push(mesh);
      }
      if (S.draggables.length > 0 && fn.frameScene) fn.frameScene();
      fn.refreshSceneList();
    } catch (err) { console.error('JSON import failed', err); }
  };
  reader.readAsText(file);
  e.target.value = '';
}
