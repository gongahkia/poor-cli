import { S } from './state.js';
import { FURNITURE_NAMES } from './furniture.js';
export function initSvgExport() {
  document.getElementById('export-svg-btn').addEventListener('click', exportSvg);
}
function getLabel(m) {
  if (m.userData.name) return m.userData.name;
  if (m.userData.furnitureType) return FURNITURE_NAMES[m.userData.furnitureType] || m.userData.furnitureType;
  if (m.userData.isWall) return 'Wall';
  return '';
}
function exportSvg() {
  if (S.draggables.length === 0) return;
  // compute bounding box in XZ
  let xMin = Infinity, xMax = -Infinity, zMin = Infinity, zMax = -Infinity;
  for (const m of S.draggables) {
    if (!m.visible) continue;
    const p = m.geometry.parameters;
    const w = p ? p.width : 1, d = p ? p.depth : 1;
    const rot = m.rotation.y;
    const halfX = (Math.abs(w * Math.cos(rot)) + Math.abs(d * Math.sin(rot))) / 2;
    const halfZ = (Math.abs(w * Math.sin(rot)) + Math.abs(d * Math.cos(rot))) / 2;
    xMin = Math.min(xMin, m.position.x - halfX);
    xMax = Math.max(xMax, m.position.x + halfX);
    zMin = Math.min(zMin, m.position.z - halfZ);
    zMax = Math.max(zMax, m.position.z + halfZ);
  }
  const pad = 0.5;
  xMin -= pad; zMin -= pad; xMax += pad; zMax += pad;
  const sceneW = xMax - xMin, sceneD = zMax - zMin;
  const pxPerM = 80; // pixels per meter
  const svgW = sceneW * pxPerM, svgH = sceneD * pxPerM;
  const toX = (x) => (x - xMin) * pxPerM;
  const toY = (z) => (z - zMin) * pxPerM; // Z maps to SVG Y (top-down)
  const parts = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${svgW.toFixed(0)}" height="${svgH.toFixed(0)}" viewBox="0 0 ${svgW.toFixed(1)} ${svgH.toFixed(1)}">`);
  parts.push(`<rect width="100%" height="100%" fill="#fff"/>`);
  // grid lines every 1m
  parts.push('<g stroke="#e0e0e0" stroke-width="0.5">');
  for (let x = Math.ceil(xMin); x <= Math.floor(xMax); x++) {
    parts.push(`<line x1="${toX(x).toFixed(1)}" y1="0" x2="${toX(x).toFixed(1)}" y2="${svgH.toFixed(1)}"/>`);
  }
  for (let z = Math.ceil(zMin); z <= Math.floor(zMax); z++) {
    parts.push(`<line x1="0" y1="${toY(z).toFixed(1)}" x2="${svgW.toFixed(1)}" y2="${toY(z).toFixed(1)}"/>`);
  }
  parts.push('</g>');
  // objects
  for (const m of S.draggables) {
    if (!m.visible) continue;
    const p = m.geometry.parameters;
    const w = p ? p.width : 1, d = p ? p.depth : 1;
    const cx = toX(m.position.x), cy = toY(m.position.z);
    const rw = w * pxPerM, rd = d * pxPerM;
    const rotDeg = -(m.rotation.y * 180 / Math.PI); // SVG rotation convention
    const color = '#' + (m.material?.color?.getHexString() ?? '888888');
    const isWall = m.userData.isWall;
    const fillOpacity = isWall ? 0.7 : 0.35;
    const strokeColor = isWall ? '#444' : '#333';
    const strokeW = isWall ? 1.5 : 0.8;
    parts.push(`<g transform="translate(${cx.toFixed(1)},${cy.toFixed(1)}) rotate(${rotDeg.toFixed(1)})">`);
    parts.push(`<rect x="${(-rw/2).toFixed(1)}" y="${(-rd/2).toFixed(1)}" width="${rw.toFixed(1)}" height="${rd.toFixed(1)}" fill="${color}" fill-opacity="${fillOpacity}" stroke="${strokeColor}" stroke-width="${strokeW}"/>`);
    const label = getLabel(m);
    if (label && !isWall) {
      const fs = Math.min(10, Math.min(rw, rd) * 0.4);
      if (fs >= 4) {
        parts.push(`<text x="0" y="${(fs * 0.35).toFixed(1)}" text-anchor="middle" font-size="${fs.toFixed(1)}" font-family="system-ui, sans-serif" fill="#222">${escXml(label)}</text>`);
      }
    }
    parts.push('</g>');
  }
  // room labels
  const rooms = {};
  for (const m of S.draggables) {
    if (!m.visible || !m.userData.room) continue;
    const room = m.userData.room;
    if (!rooms[room]) rooms[room] = { xs: [], zs: [] };
    rooms[room].xs.push(m.position.x);
    rooms[room].zs.push(m.position.z);
  }
  for (const [name, { xs, zs }] of Object.entries(rooms)) {
    const avgX = xs.reduce((a, b) => a + b, 0) / xs.length;
    const avgZ = zs.reduce((a, b) => a + b, 0) / zs.length;
    parts.push(`<text x="${toX(avgX).toFixed(1)}" y="${toY(avgZ).toFixed(1)}" text-anchor="middle" font-size="14" font-weight="bold" font-family="system-ui, sans-serif" fill="#1a7a4a" opacity="0.7">${escXml(name)}</text>`);
  }
  // scale bar (bottom-right)
  const barLen = 1 * pxPerM; // 1m bar
  const barX = svgW - barLen - 10, barY = svgH - 15;
  parts.push(`<line x1="${barX}" y1="${barY}" x2="${barX + barLen}" y2="${barY}" stroke="#333" stroke-width="2"/>`);
  parts.push(`<line x1="${barX}" y1="${barY - 4}" x2="${barX}" y2="${barY + 4}" stroke="#333" stroke-width="1.5"/>`);
  parts.push(`<line x1="${barX + barLen}" y1="${barY - 4}" x2="${barX + barLen}" y2="${barY + 4}" stroke="#333" stroke-width="1.5"/>`);
  parts.push(`<text x="${barX + barLen / 2}" y="${barY - 6}" text-anchor="middle" font-size="10" font-family="system-ui, sans-serif" fill="#333">1m</text>`);
  parts.push('</svg>');
  const blob = new Blob([parts.join('\n')], { type: 'image/svg+xml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'haus-floorplan.svg'; a.click();
  URL.revokeObjectURL(url);
}
function escXml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
