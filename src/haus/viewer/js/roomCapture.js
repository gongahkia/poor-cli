import { fn } from './state.js';

const WALL_VIEWS = ['north', 'east', 'south', 'west'];
const MAX_CAPTURE_PHOTOS = 12;
const MAX_CAPTURE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

export function initRoomCapture() {
  const input = document.getElementById('room-capture-input');
  const buildBtn = document.getElementById('room-build-btn');
  if (!input || !buildBtn) return;
  buildBtn.addEventListener('click', buildRoomCapture);
}

function status(text, isError = false) {
  const el = document.getElementById('room-capture-status');
  if (!el) return;
  el.textContent = text;
  el.style.color = isError ? 'var(--chat-err-fg)' : 'var(--fg-accent)';
}

function numberValue(id, { min, max, label }) {
  const el = document.getElementById(id);
  const value = Number.parseFloat(el?.value || '');
  if (!Number.isFinite(value)) throw new Error(`${label} must be numeric`);
  if (value < min || value > max) throw new Error(`${label} must be between ${min} and ${max}m`);
  return value;
}

function errorText(body, fallback) {
  if (typeof body?.error === 'string') return body.error;
  if (body?.error?.message) return body.error.message;
  return fallback;
}

function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error(`Could not read ${file.name}`));
    reader.onload = () => resolve(String(reader.result || ''));
    reader.readAsDataURL(file);
  });
}

async function roomPhotos() {
  const input = document.getElementById('room-capture-input');
  const files = Array.from(input?.files || []);
  if (files.length > MAX_CAPTURE_PHOTOS) throw new Error(`Use ${MAX_CAPTURE_PHOTOS} photos or fewer`);
  const out = [];
  for (let i = 0; i < files.length; i += 1) {
    const file = files[i];
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) throw new Error(`${file.name} must be JPEG, PNG, or WebP`);
    if (file.size > MAX_CAPTURE_BYTES) throw new Error(`${file.name} is larger than 5 MB`);
    out.push({
      name: file.name,
      view: WALL_VIEWS[i % WALL_VIEWS.length],
      data_url: await readFileDataUrl(file),
    });
  }
  return out;
}

function parseOpenings() {
  const raw = document.getElementById('room-openings')?.value?.trim() || '';
  if (!raw) return [];
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error('openings must be a JSON array');
  return parsed;
}

function isCapturedShellItem(item) {
  const name = String(item?.name || '');
  return name.startsWith('captured_')
    || name.startsWith('room_photo_')
    || item?.type === 'reference_image'
    || Boolean(item?.room_capture_opening);
}

function preserveUserItems(nextLayout) {
  const current = fn.getLayoutData ? fn.getLayoutData() : null;
  const existing = Array.isArray(current?.items) ? current.items : [];
  const keep = existing.filter((item) => !isCapturedShellItem(item));
  if (keep.length > 0) nextLayout.items.push(...keep);
}

async function buildRoomCapture() {
  try {
    status('Building room...');
    const payload = {
      measurements: {
        width_m: numberValue('room-width', { min: 0.5, max: 50, label: 'width' }),
        depth_m: numberValue('room-depth', { min: 0.5, max: 50, label: 'depth' }),
        height_m: numberValue('room-height', { min: 1.8, max: 8, label: 'height' }),
      },
      openings: parseOpenings(),
      photos: await roomPhotos(),
    };
    const res = await fetch('/api/room-capture/layout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok || body.ok === false) throw new Error(errorText(body, `HTTP ${res.status}`));
    preserveUserItems(body.layout);
    fn.applyLayoutData(body.layout);
    if (fn.pushLayoutToServer) fn.pushLayoutToServer();
    status(`Built ${body.layout.items.length} item room.`);
  } catch (err) {
    console.error('room capture failed', err);
    status(err.message || String(err), true);
  }
}
