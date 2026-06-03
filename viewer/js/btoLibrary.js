import { fn } from './state.js';

const BTO_LAYOUTS = [
  {
    id: '1',
    name: '2-room orange BTO',
    url: '/corpus/library/1.json',
    walls: 21,
    scale: '0.0094',
    source: 'corpus/cleaned/1.jpg',
  },
  {
    id: '2',
    name: '4-room yellow BTO',
    url: '/corpus/library/2.json',
    walls: 25,
    scale: '0.0088',
    source: 'corpus/cleaned/2.jpg',
  },
  {
    id: '3',
    name: '3-room orange BTO',
    url: '/corpus/library/3.json',
    walls: 113,
    scale: '0.0097',
    source: 'corpus/cleaned/3.jpg',
  },
  {
    id: '4',
    name: '4-room green BTO',
    url: '/corpus/library/4.json',
    walls: 77,
    scale: '0.0088',
    source: 'corpus/cleaned/4.jpg',
  },
];

export function initBtoLibrary() {
  const picker = document.getElementById('bto-layout-picker');
  if (!picker) return;

  for (const layout of BTO_LAYOUTS) {
    const option = document.createElement('option');
    option.value = layout.id;
    option.textContent = `${layout.name} - ${layout.walls} walls`;
    option.title = `${layout.source}, scale ${layout.scale} m/px`;
    picker.appendChild(option);
  }

  picker.addEventListener('change', async () => {
    const selected = BTO_LAYOUTS.find((layout) => layout.id === picker.value);
    if (!selected) return;

    picker.disabled = true;
    try {
      const res = await fetch(selected.url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!Array.isArray(data.items)) throw new Error('layout JSON missing items array');

      fn.applyLayoutData(data);
      if (fn.pushLayoutToServer) await fn.pushLayoutToServer();
      if (fn.frameScene) fn.frameScene();
    } catch (err) {
      console.error('Failed loading BTO layout', selected, err);
      window.alert(`Failed to load ${selected.name}: ${err.message || err}`);
    } finally {
      picker.disabled = false;
      picker.value = '';
    }
  });
}
