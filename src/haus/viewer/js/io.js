import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { S, fn } from './state.js';
import { FURNITURE } from './furniture.js';
import { createSceneMaterial, prepareMeshForScene } from './scene.js';
const loader = new GLTFLoader();
export function initIO() {
  const params = new URLSearchParams(location.search);
  const glbParam = params.get('glb');
  const caseParam = params.get('case');
  if (caseParam) {
    loadCaseFromUrl(caseParam);
  } else {
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
  }
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
  fn.applyCaseData = applyCaseData;
  fn.addLayoutItem = addLayoutItem;
  fn.getLayoutData = serializeLayout;
  initCaseReviewPanel();
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
  if (item.type === 'reference_image') return 'model';
  if (item.type === 'model_part') return 'model';
  return 'furniture';
}
function materialForLayoutItem(item, kind) {
  if (item.texture_data_url) {
    const texture = new THREE.TextureLoader().load(item.texture_data_url);
    texture.colorSpace = THREE.SRGBColorSpace;
    return new THREE.MeshStandardMaterial({
      map: texture,
      color: 0xffffff,
      roughness: 0.72,
      metalness: 0.0,
      side: THREE.DoubleSide,
    });
  }
  return createSceneMaterial(kind, item.color);
}
function buildMeshFromLayoutItem(item) {
  if (!item.geo || !item.pos || item.geo.length < 3 || item.pos.length < 3) {
    console.warn('Skipping malformed layout item', item);
    return null;
  }

  const kind = materialKindForItem(item);
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(item.geo[0], item.geo[1], item.geo[2]),
    materialForLayoutItem(item, kind)
  );
  prepareMeshForScene(mesh, kind, item.color, { replaceMaterial: false });
  mesh.position.set(item.pos[0], item.pos[1], item.pos[2]);
  mesh.rotation.y = item.rot;
  mesh.userData.draggable = true;
  mesh.visible = item.visible !== false;

  if (item.type === 'wall') {
    mesh.userData.isWall = true;
    mesh.userData.baseY = item.geo[1] / 2;
    if (item.hdb_type) mesh.userData.hdbType = item.hdb_type;
    if (item.wall_type) mesh.userData.wallType = item.wall_type;
    if (item.hdb_thickness_m !== undefined) mesh.userData.hdbThicknessM = item.hdb_thickness_m;
    if (item.thickness_m !== undefined) mesh.userData.thicknessM = item.thickness_m;
    S.userWalls.push(mesh);
  } else if (item.type === 'model_part' || item.type === 'reference_image') {
    mesh.userData.isModelPart = true;
    mesh.userData.layoutType = item.type;
    if (item.texture_data_url) mesh.userData.textureDataUrl = item.texture_data_url;
    if (item.label) mesh.userData.label = item.label;
    if (item.source_view) mesh.userData.sourceView = item.source_view;
    if (item.room_capture_opening) mesh.userData.roomCaptureOpening = item.room_capture_opening;
    S.modelParts.push(mesh);
  } else {
    mesh.userData.baseY = item.geo[1] / 2;
    if (item.furnitureType) mesh.userData.furnitureType = item.furnitureType;
    if (item.catalog) mesh.userData.catalog = item.catalog;
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
  for (const [index, m] of S.draggables.entries()) {
    if (!m.visible) continue;
    const clone = m.clone();
    const ol = clone.getObjectByName('_outline'); if (ol) clone.remove(ol);
    const cs = clone.getObjectByName('_contact_shadow'); if (cs) clone.remove(cs);
    clone.userData = {
      ...clone.userData,
      hausSemantic: semanticRecordForMesh(m, index),
      units: 'meters',
    };
    exportScene.add(clone);
  }
  const exporter = new GLTFExporter();
  exporter.parse(exportScene, (result) => {
    downloadBlob(new Blob([result], { type: 'application/octet-stream' }), 'haus-export.glb');
  }, (err) => { console.error('GLB export failed', err); }, { binary: true });
}
function serializeLayout() {
  const items = [];
  const semanticObjects = [];
  for (const [index, m] of S.draggables.entries()) {
    const entry = { pos: [m.position.x, m.position.y, m.position.z], rot: m.rotation.y, visible: m.visible };
    if (m.userData.isWall) {
      entry.type = 'wall';
      entry.geo = [m.geometry.parameters.width, m.geometry.parameters.height, m.geometry.parameters.depth];
      entry.color = m.material.color.getHex();
      if (m.userData.hdbType) entry.hdb_type = m.userData.hdbType;
      if (m.userData.wallType) entry.wall_type = m.userData.wallType;
      if (m.userData.hdbThicknessM !== undefined) entry.hdb_thickness_m = m.userData.hdbThicknessM;
      if (m.userData.thicknessM !== undefined) entry.thickness_m = m.userData.thicknessM;
    } else if (m.userData.isModelPart) {
      entry.type = m.userData.layoutType || 'model_part';
      const size = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
      entry.geo = [size.x, size.y, size.z];
      entry.color = m.material?.color?.getHex() ?? 0x888888;
      if (m.userData.textureDataUrl) entry.texture_data_url = m.userData.textureDataUrl;
      if (m.userData.label) entry.label = m.userData.label;
      if (m.userData.sourceView) entry.source_view = m.userData.sourceView;
      if (m.userData.roomCaptureOpening) entry.room_capture_opening = m.userData.roomCaptureOpening;
    } else {
      entry.type = 'furniture';
      entry.furnitureType = m.userData.furnitureType || null;
      entry.geo = [m.geometry.parameters.width, m.geometry.parameters.height, m.geometry.parameters.depth];
      entry.color = m.material.color.getHex();
      if (m.userData.catalog) entry.catalog = m.userData.catalog;
    }
    if (m.userData.name) entry.name = m.userData.name;
    if (m.userData.room) entry.room = m.userData.room;
    items.push(entry);
    semanticObjects.push(semanticRecordForMesh(m, index));
  }
  const layout = { version: 1, items };
  if (S.layoutMetadata) layout.metadata = S.layoutMetadata;
  if (Array.isArray(S.layoutRooms) && S.layoutRooms.length > 0) layout.rooms = S.layoutRooms;
  if (S.caseReview) appendCaseReviewToLayout(layout);
  if (S.roomCapture) layout.room_capture = S.roomCapture;
  layout.semantic = {
    schema: 'haus.semantic_layout.v1',
    units: 'meters',
    objects: semanticObjects,
    export_notes: [
      'GLB/JSON exports preserve Haus object semantics for visualization and future BIM mapping.',
      'This is not an IFC export or code-compliance certificate.',
    ],
  };
  return layout;
}

function semanticKindForMesh(m) {
  if (m.userData.isWall) return 'wall';
  if (m.userData.isModelPart) return 'model_part';
  const type = m.userData.furnitureType || '';
  if (['sink', 'toilet', 'shower'].includes(type)) return 'fixture';
  if (['fridge', 'washer', 'kitchen_counter'].includes(type)) return 'appliance';
  return 'furniture';
}

function meshDimensions(m) {
  if (m.geometry?.parameters?.width) {
    return {
      width: m.geometry.parameters.width,
      height: m.geometry.parameters.height,
      depth: m.geometry.parameters.depth,
    };
  }
  const size = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
  return { width: size.x, height: size.y, depth: size.z };
}

function semanticRecordForMesh(m, index) {
  return {
    index,
    semantic_kind: semanticKindForMesh(m),
    furniture_type: m.userData.furnitureType || null,
    name: m.userData.name || null,
    room: m.userData.room || null,
    position_m: { x: m.position.x, y: m.position.y, z: m.position.z },
    rotation_y_rad: m.rotation.y,
    dimensions_m: meshDimensions(m),
  };
}

function isCasePayload(data) {
  return Boolean(
    data
    && Array.isArray(data.items)
    && (
      data.case_id
      || data.case_schema_version
      || Array.isArray(data._baseline_items)
      || Array.isArray(data.compliance_findings)
    )
  );
}

function itemKey(item, index = null) {
  if (item?.name) return `name:${item.name}`;
  if (index !== null) return `index:${index}`;
  return null;
}

function arraysClose(a, b, epsilon = 0.001) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  return a.every((value, index) => Math.abs(Number(value) - Number(b[index])) <= epsilon);
}

function sameLayoutItem(a, b) {
  if (!a || !b) return false;
  const sameVisible = (a.visible !== false) === (b.visible !== false);
  return arraysClose(a.pos, b.pos)
    && arraysClose(a.geo, b.geo)
    && Math.abs(Number(a.rot || 0) - Number(b.rot || 0)) <= 0.001
    && sameVisible;
}

function findingNameSet(findings) {
  const names = new Set();
  for (const finding of findings || []) {
    if (finding?.element_name) names.add(String(finding.element_name));
  }
  return names;
}

function findingIndexSet(findings) {
  const indexes = new Set();
  for (const finding of findings || []) {
    if (Number.isInteger(finding?.element_index)) indexes.add(finding.element_index);
  }
  return indexes;
}

function cloneCaseData(data) {
  return JSON.parse(JSON.stringify(data));
}

function appendCaseReviewToLayout(layout) {
  const c = S.caseReview;
  layout.case_schema_version = c.case_schema_version ?? 1;
  layout.case_id = c.case_id;
  layout.created_at = c.created_at;
  layout.updated_at = c.updated_at;
  layout.design_status = c.design_status;
  layout.revise_count = c.revise_count;
  layout.pinned_proposal_id = c.pinned_proposal_id ?? null;
  layout.vendor_cache_key = c.vendor_cache_key ?? null;
  layout.brief = c.brief || {};
  layout.compliance_findings = cloneCaseData(c.compliance_findings || []);
  layout.approval_state = c.approval_state ?? null;
  layout.vendor_handoff = c.vendor_handoff ?? null;
  layout._baseline_items = cloneCaseData(c._baseline_items || []);
  if (Array.isArray(c._baseline_protected_walls)) {
    layout._baseline_protected_walls = cloneCaseData(c._baseline_protected_walls);
  }
}

function clearCaseOverlay() {
  if (!S.caseOverlayGroup) return;
  S.scene.remove(S.caseOverlayGroup);
  S.caseOverlayGroup.traverse((child) => {
    child.geometry?.dispose?.();
    if (Array.isArray(child.material)) {
      child.material.forEach((mat) => mat.dispose?.());
    } else {
      child.material?.dispose?.();
    }
  });
  S.caseOverlayGroup = null;
}

function clearCaseReview() {
  clearCaseOverlay();
  S.caseReview = null;
  const panel = document.getElementById('case-review-section');
  if (panel) panel.style.display = 'none';
}

function caseGhostMaterial(kind) {
  const colors = {
    removed: 0xef4444,
    changed: 0xf59e0b,
    baseline: 0x94a3b8,
  };
  const mat = new THREE.MeshStandardMaterial({
    color: colors[kind] || colors.baseline,
    transparent: true,
    opacity: kind === 'removed' ? 0.62 : 0.36,
    roughness: 0.55,
    metalness: 0.02,
    depthWrite: false,
  });
  if (kind === 'removed') mat.emissive = new THREE.Color(0x4a0505);
  return mat;
}

function buildGhostFromItem(item, diffKind) {
  if (!item.geo || !item.pos || item.geo.length < 3 || item.pos.length < 3) return null;
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(item.geo[0], item.geo[1], item.geo[2]),
    caseGhostMaterial(diffKind),
  );
  mesh.position.set(item.pos[0], item.pos[1], item.pos[2]);
  mesh.rotation.y = item.rot || 0;
  mesh.visible = item.visible !== false;
  mesh.userData.caseGhost = diffKind;
  mesh.userData.name = item.name || '';
  mesh.raycast = () => {};
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color: diffKind === 'removed' ? 0xffd1d1 : 0xffe7a3 }),
  );
  edges.name = '_case_diff_edges';
  mesh.add(edges);
  return mesh;
}

function addCaseOutline(mesh, color = 0xef4444) {
  const old = mesh.getObjectByName('_case_finding_outline');
  if (old) mesh.remove(old);
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color, linewidth: 2 }),
  );
  outline.name = '_case_finding_outline';
  mesh.add(outline);
}

function tintCurrentMeshForCase(mesh, diffKind) {
  if (!mesh?.material?.color) return;
  if (diffKind === 'finding') {
    mesh.material.color.setHex(0xef4444);
    if (mesh.material.emissive) mesh.material.emissive.setHex(0x3b0606);
    addCaseOutline(mesh, 0xffd1d1);
  } else if (diffKind === 'added') {
    addCaseOutline(mesh, 0x38bdf8);
  } else if (diffKind === 'changed') {
    addCaseOutline(mesh, 0xf59e0b);
  }
}

function renderCaseReviewOverlay(caseData) {
  clearCaseOverlay();
  const baseline = Array.isArray(caseData._baseline_items) ? caseData._baseline_items : [];
  if (!baseline.length) return;

  const findings = Array.isArray(caseData.compliance_findings) ? caseData.compliance_findings : [];
  const findingNames = findingNameSet(findings);
  const currentByKey = new Map();
  caseData.items.forEach((item, index) => {
    const key = itemKey(item, index);
    if (key) currentByKey.set(key, item);
  });

  const group = new THREE.Group();
  group.name = 'case-review-baseline-overlay';
  let overlayCount = 0;
  baseline.forEach((item, index) => {
    const key = itemKey(item, index);
    const current = key ? currentByKey.get(key) : null;
    const isFinding = item.name && findingNames.has(String(item.name));
    let diffKind = null;
    if (!current) diffKind = isFinding ? 'removed' : 'baseline';
    else if (!sameLayoutItem(item, current)) diffKind = isFinding ? 'removed' : 'changed';
    if (!diffKind || (diffKind === 'baseline' && !isFinding)) return;
    const ghost = buildGhostFromItem(item, diffKind);
    if (!ghost) return;
    group.add(ghost);
    overlayCount += 1;
  });
  if (overlayCount > 0) {
    S.scene.add(group);
    S.caseOverlayGroup = group;
  }
}

function applyCaseStylingToCurrentMeshes(caseData) {
  const baselineByKey = new Map();
  const baseline = Array.isArray(caseData._baseline_items) ? caseData._baseline_items : [];
  baseline.forEach((item, index) => {
    const key = itemKey(item, index);
    if (key) baselineByKey.set(key, item);
  });
  const findings = Array.isArray(caseData.compliance_findings) ? caseData.compliance_findings : [];
  const names = findingNameSet(findings);
  const indexes = findingIndexSet(findings);
  S.draggables.forEach((mesh, index) => {
    const name = mesh.userData.name;
    if ((name && names.has(String(name))) || indexes.has(index)) {
      tintCurrentMeshForCase(mesh, 'finding');
      return;
    }
    const key = name ? `name:${name}` : `index:${index}`;
    const baselineItem = baselineByKey.get(key);
    if (!baselineItem) {
      tintCurrentMeshForCase(mesh, 'added');
      return;
    }
    const currentItem = caseData.items[index] || null;
    if (currentItem && !sameLayoutItem(baselineItem, currentItem)) tintCurrentMeshForCase(mesh, 'changed');
  });
}

function updateCaseReviewPanel(caseData) {
  const panel = document.getElementById('case-review-section');
  if (!panel) return;
  panel.style.display = '';
  const summary = document.getElementById('case-review-summary');
  const findingsEl = document.getElementById('case-findings-list');
  const findings = Array.isArray(caseData.compliance_findings) ? caseData.compliance_findings : [];
  const errors = findings.filter((f) => f?.severity === 'error').length;
  summary.textContent = `${caseData.design_status || 'case'} · revise ${caseData.revise_count || 0} · ${findings.length} finding${findings.length === 1 ? '' : 's'} (${errors} error${errors === 1 ? '' : 's'})`;
  findingsEl.innerHTML = '';
  for (const finding of findings.slice(0, 8)) {
    const row = document.createElement('button');
    row.className = 'case-finding-row';
    row.type = 'button';
    const title = document.createElement('strong');
    title.textContent = finding.element_name || finding.rule_id || 'finding';
    const meta = document.createElement('span');
    meta.textContent = finding.rule_id || '';
    row.appendChild(title);
    row.appendChild(meta);
    row.title = finding.reason || '';
    row.addEventListener('click', () => {
      const target = S.draggables.find((m) => m.userData.name === finding.element_name);
      if (target) {
        fn.selectFurniture(target);
      } else if (S.caseOverlayGroup) {
        const ghost = S.caseOverlayGroup.children.find((m) => m.userData.name === finding.element_name);
        if (ghost) {
          const box = new THREE.Box3().setFromObject(ghost);
          const center = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          const dist = Math.max(size.x, size.y, size.z, 1) * 2;
          const dir = S.camera.position.clone().sub(S.orbit.target).normalize();
          S.orbit.target.copy(center);
          S.camera.position.copy(center).addScaledVector(dir, dist);
          S.orbit.update();
        }
      }
    });
    findingsEl.appendChild(row);
  }
}

function initCaseReviewPanel() {
  const toggle = document.getElementById('case-baseline-toggle');
  if (toggle) {
    toggle.addEventListener('change', () => {
      if (S.caseOverlayGroup) S.caseOverlayGroup.visible = toggle.checked;
    });
  }
}

async function loadCaseFromUrl(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    applyCaseData(data);
    if (fn.frameScene) fn.frameScene();
  } catch (err) {
    console.error('Case load failed', err);
    window.alert(`Failed to load Case JSON: ${err.message || err}`);
  }
}

function applyCaseData(data, { recordUndo = true, frame = true } = {}) {
  if (!Array.isArray(data.items)) {
    console.warn('Ignoring malformed Case payload: items missing array');
    return;
  }
  S.caseReview = cloneCaseData(data);
  applySceneLayout(data, { recordUndo, frame, preserveCaseReview: true });
  renderCaseReviewOverlay(data);
  applyCaseStylingToCurrentMeshes(data);
  updateCaseReviewPanel(data);
  fn.refreshSceneList();
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
  clearCaseReview();
  clearModelParts();
  while (S.draggables.length) S.scene.remove(S.draggables.pop());
  S.userWalls.length = 0;
  S.hiddenObjects.length = 0;
  S.layoutMetadata = null;
  S.layoutRooms = [];
  S.roomCapture = null;
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
function applySceneLayout(data, { recordUndo = true, frame = true, preserveCaseReview = false } = {}) {
  if (!Array.isArray(data.items)) {
    console.warn('Ignoring malformed MCP layout payload: items missing array');
    return;
  }
  const prev = serializeLayout();
  if (!preserveCaseReview) clearCaseReview();
  S.layoutMetadata = data.metadata && typeof data.metadata === 'object' ? data.metadata : null;
  S.layoutRooms = Array.isArray(data.rooms) ? data.rooms : [];
  S.roomCapture = data.room_capture && typeof data.room_capture === 'object' ? data.room_capture : null;
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
function applyLayoutData(data, { recordUndo = true, frame = true } = {}) {
  if (isCasePayload(data)) {
    applyCaseData(data, { recordUndo, frame });
    return;
  }
  applySceneLayout(data, { recordUndo, frame });
}
function addLayoutItem(item) {
  const mesh = buildMeshFromLayoutItem(item);
  if (!mesh) return false;
  S.scene.add(mesh);
  S.draggables.push(mesh);
  fn.pushUndo({ type: 'add', mesh, inUserWalls: Boolean(mesh.userData.isWall) });
  fn.refreshSceneList();
  if (fn.pushLayoutToServer) fn.pushLayoutToServer();
  if (fn.selectFurniture) fn.selectFurniture(mesh);
  return true;
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
      applyLayoutData(data);
    } catch (err) { console.error('JSON import failed', err); }
  };
  reader.readAsText(file);
  e.target.value = '';
}
