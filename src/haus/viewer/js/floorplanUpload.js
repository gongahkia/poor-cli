import { S, fn } from './state.js';

let lastFile = null;
let lastDataUrl = '';

function $(id) {
  return document.getElementById(id);
}

function setStatus(text, tone = '') {
  const el = $('floorplan-upload-status');
  if (!el) return;
  el.textContent = text;
  el.style.color = tone === 'error' ? 'var(--chat-err-fg)' : 'var(--fg-accent)';
}

function numberValue(id) {
  const raw = $(id)?.value;
  if (!raw) return null;
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function calibratedScale() {
  const px = numberValue('floorplan-known-px');
  const meters = numberValue('floorplan-known-m');
  if (!px || !meters) return null;
  return meters / px;
}

function appendLine(root, label, value) {
  const line = document.createElement('div');
  line.textContent = `${label}: ${value}`;
  root.appendChild(line);
}

function renderReview(body) {
  const section = $('floorplan-review-section');
  const summary = $('floorplan-review-summary');
  const warnings = $('floorplan-review-warnings');
  if (!section || !summary || !warnings) return;
  const meta = body.layout?.metadata || {};
  section.style.display = '';
  summary.innerHTML = '';
  warnings.innerHTML = '';
  appendLine(summary, 'file', meta.source_filename || lastFile?.name || 'uploaded plan');
  appendLine(summary, 'walls', meta.wall_count ?? body.metadata?.walls?.total_segments ?? 0);
  appendLine(summary, 'openings', meta.opening_count ?? body.metadata?.openings?.total ?? 0);
  appendLine(summary, 'scale', meta.scale_m_per_px ? `${Number(meta.scale_m_per_px).toFixed(5)} m/px` : 'unverified');
  const warningList = Array.isArray(body.warnings) ? body.warnings : [];
  if (!warningList.length) {
    appendLine(warnings, 'status', 'ready for visual review');
  } else {
    warningList.forEach((warning) => appendLine(warnings, 'warning', warning));
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('failed to read file'));
    reader.readAsDataURL(file);
  });
}

function imageSize(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.width, height: img.height });
    img.onerror = () => reject(new Error('failed to decode image'));
    img.src = dataUrl;
  });
}

async function useImageOnly() {
  if (!lastFile) {
    setStatus('Upload a floor plan first.', 'error');
    return;
  }
  try {
    if (!lastDataUrl) lastDataUrl = await fileToDataUrl(lastFile);
    const size = await imageSize(lastDataUrl);
    const aspect = Math.max(0.1, size.width / Math.max(size.height, 1));
    const depth = 20;
    const width = depth * aspect;
    fn.applyLayoutData({
      version: 1,
      metadata: {
        source_type: 'upload_overlay',
        source_filename: lastFile.name,
        note: 'image-only reference; draw or place objects manually',
      },
      items: [{
        type: 'reference_image',
        name: 'floor_plan_reference',
        label: lastFile.name,
        pos: [0, 0.01, 0],
        geo: [width, 0.02, depth],
        rot: 0,
        color: 16777215,
        visible: true,
        texture_data_url: lastDataUrl,
      }],
    });
    if (fn.pushLayoutToServer) await fn.pushLayoutToServer();
    if (fn.frameScene) fn.frameScene();
    setStatus('Loaded uploaded image as an editable reference.');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  }
}

async function uploadFloorPlan(file) {
  if (!file) return;
  lastFile = file;
  lastDataUrl = '';
  setStatus('Vectorizing floor plan...');
  const form = new FormData();
  form.append('file', file);
  const scale = calibratedScale();
  if (scale) form.append('scale_m_per_px', String(scale));
  const wallHeight = numberValue('floorplan-wall-height');
  if (wallHeight) form.append('wall_height_m', String(wallHeight));
  form.append('clean', $('floorplan-clean')?.checked === false ? 'false' : 'true');
  try {
    const res = await fetch('/api/floorplans/vectorize', { method: 'POST', body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || body.ok === false) throw new Error(body.error || `HTTP ${res.status}`);
    S.uploadedFloorPlan = {
      filename: file.name,
      upload_id: body.artifacts?.upload_id || null,
      warnings: body.warnings || [],
    };
    fn.applyLayoutData(body.layout);
    if (fn.pushLayoutToServer) await fn.pushLayoutToServer();
    if (fn.frameScene) fn.frameScene();
    renderReview(body);
    setStatus(`Loaded ${file.name}. Review extraction before planning.`);
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  }
}

function bindUploadInput(id) {
  const input = $(id);
  if (!input) return;
  input.addEventListener('change', () => {
    const file = input.files?.[0];
    uploadFloorPlan(file);
    input.value = '';
  });
}

export function initFloorplanUpload() {
  bindUploadInput('floorplan-upload-input');
  bindUploadInput('floorplan-panel-input');
  $('floorplan-overlay-only')?.addEventListener('click', useImageOnly);
  $('floorplan-clear')?.addEventListener('click', async () => {
    if (fn.clearLayoutAndSync) await fn.clearLayoutAndSync({ confirmWithMcp: false });
    setStatus('Layout cleared.');
  });
}
