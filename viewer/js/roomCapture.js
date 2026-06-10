import { fn } from './state.js';

const WALL_VIEWS = ['north', 'east', 'south', 'west'];

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

function numberValue(id) {
  const el = document.getElementById(id);
  const value = Number.parseFloat(el?.value || '');
  if (!Number.isFinite(value)) throw new Error(`${id} must be numeric`);
  return value;
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
  const files = Array.from(input?.files || []).slice(0, 12);
  const out = [];
  for (let i = 0; i < files.length; i += 1) {
    const file = files[i];
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
        width_m: numberValue('room-width'),
        depth_m: numberValue('room-depth'),
        height_m: numberValue('room-height'),
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
    if (!res.ok || body.ok === false) throw new Error(body.error || `HTTP ${res.status}`);
    preserveUserItems(body.layout);
    fn.applyLayoutData(body.layout);
    if (fn.pushLayoutToServer) fn.pushLayoutToServer();
    status(`Built ${body.layout.items.length} item room.`);
  } catch (err) {
    console.error('room capture failed', err);
    status(err.message || String(err), true);
  }
}
