import * as THREE from 'three';
import { S, fn } from './state.js';

let overlayGroup = null;
let clearTimer = 0;

const COLOR_CLEAR = 0x44ddaa;
const COLOR_BLOCKED = 0xdd4444;
const COLOR_TARGET = 0x4a8cff;

export function initSightline() {
  overlayGroup = new THREE.Group();
  overlayGroup.name = '_sightline_overlay';
  S.scene.add(overlayGroup);

  fn.showSightlineOverlay = showSightlineOverlay;
  fn.clearSightlineOverlay = clearSightlineOverlay;
}

function disposeNode(node) {
  if (node.geometry) node.geometry.dispose();
  const mat = node.material;
  if (Array.isArray(mat)) mat.forEach((m) => m?.dispose?.());
  else mat?.dispose?.();
}

function clearOverlayChildren() {
  if (!overlayGroup) return;
  while (overlayGroup.children.length > 0) {
    const child = overlayGroup.children.pop();
    if (child) disposeNode(child);
  }
}

function toIndex(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) {
    return Math.trunc(Number(value));
  }
  return null;
}

function uniqueIndices(values) {
  const seen = new Set();
  const out = [];
  for (const v of values) {
    const idx = toIndex(v);
    if (idx === null || seen.has(idx)) continue;
    seen.add(idx);
    out.push(idx);
  }
  return out;
}

function meshEyePoint(mesh) {
  const h = mesh?.geometry?.parameters?.height;
  const eyeLift = typeof h === 'number' ? Math.max(0.2, Math.min(0.8, h * 0.35)) : 0.5;
  return new THREE.Vector3(mesh.position.x, mesh.position.y + eyeLift, mesh.position.z);
}

function marker(point, color, radius = 0.06) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 12, 12),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 }),
  );
  mesh.position.copy(point);
  mesh.renderOrder = 1000;
  return mesh;
}

function lineSegment(start, end, color, dashed = false) {
  const geo = new THREE.BufferGeometry().setFromPoints([start, end]);
  const mat = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 0.14, gapSize: 0.09, transparent: true, opacity: 0.95 })
    : new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.95 });
  const line = new THREE.Line(geo, mat);
  if (dashed && line.computeLineDistances) line.computeLineDistances();
  line.renderOrder = 999;
  return line;
}

function blockerOutline(mesh) {
  const edges = new THREE.EdgesGeometry(mesh.geometry);
  const mat = new THREE.LineBasicMaterial({ color: COLOR_BLOCKED, transparent: true, opacity: 0.95 });
  const lines = new THREE.LineSegments(edges, mat);
  lines.position.copy(mesh.position);
  lines.rotation.copy(mesh.rotation);
  lines.scale.copy(mesh.scale);
  lines.renderOrder = 1001;
  return lines;
}

function pickFirstBlockPoint(start, end, blockerIndices) {
  const seg = end.clone().sub(start);
  const lenSq = seg.lengthSq();
  if (lenSq < 1e-8) return end.clone();

  let bestT = 1;
  for (const idx of blockerIndices) {
    const mesh = S.draggables[idx];
    if (!mesh) continue;
    const center = mesh.position.clone();
    const rel = center.sub(start);
    const t = Math.max(0, Math.min(1, rel.dot(seg) / lenSq));
    if (t < bestT) bestT = t;
  }

  return start.clone().addScaledVector(seg, bestT);
}

function scheduleAutoClear() {
  if (clearTimer) clearTimeout(clearTimer);
  clearTimer = setTimeout(() => {
    clearSightlineOverlay();
  }, 12000);
}

function clearSightlineOverlay() {
  clearOverlayChildren();
  if (clearTimer) {
    clearTimeout(clearTimer);
    clearTimer = 0;
  }
}

function showSightlineOverlay({
  indexFrom,
  indexTo,
  blockerIndices = [],
}) {
  if (!overlayGroup) return;

  clearOverlayChildren();

  const srcIdx = toIndex(indexFrom);
  const dstIdx = toIndex(indexTo);
  if (srcIdx === null || dstIdx === null) return;

  const src = S.draggables[srcIdx];
  const dst = S.draggables[dstIdx];
  if (!src || !dst) return;

  const blockers = uniqueIndices(blockerIndices)
    .filter((idx) => idx !== srcIdx && idx !== dstIdx)
    .filter((idx) => !!S.draggables[idx]);

  const start = meshEyePoint(src);
  const end = meshEyePoint(dst);

  overlayGroup.add(marker(start, COLOR_CLEAR, 0.07));
  overlayGroup.add(marker(end, COLOR_TARGET, 0.07));

  if (blockers.length === 0) {
    overlayGroup.add(lineSegment(start, end, COLOR_CLEAR, false));
  } else {
    const blockPoint = pickFirstBlockPoint(start, end, blockers);
    overlayGroup.add(lineSegment(start, blockPoint, COLOR_CLEAR, false));
    overlayGroup.add(lineSegment(blockPoint, end, COLOR_BLOCKED, true));

    for (const idx of blockers) {
      const blockerMesh = S.draggables[idx];
      overlayGroup.add(blockerOutline(blockerMesh));
      overlayGroup.add(marker(meshEyePoint(blockerMesh), COLOR_BLOCKED, 0.05));
    }
  }

  scheduleAutoClear();
}
