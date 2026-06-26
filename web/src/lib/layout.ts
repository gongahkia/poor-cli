import type { LayoutData, LayoutItem } from './types';
import { emptyLayout, withIds } from './types';

export const FURNITURE: Record<string, { label: string; geo: [number, number, number]; color: number }> = {
  sofa_3: { label: 'Sofa', geo: [2.1, 0.75, 0.9], color: 0x59656a },
  bed_queen: { label: 'Queen bed', geo: [1.6, 0.55, 2.0], color: 0x6d7d86 },
  desk: { label: 'Desk', geo: [1.2, 0.75, 0.6], color: 0x85745f },
  dining_4: { label: 'Dining table', geo: [1.4, 0.75, 0.85], color: 0x786d62 },
  wardrobe: { label: 'Wardrobe', geo: [1.4, 2.1, 0.55], color: 0x707a72 },
  tv_console: { label: 'TV console', geo: [1.6, 0.5, 0.42], color: 0x4b5563 },
};

export function normalizeLayout(input: unknown): LayoutData {
  if (!input || typeof input !== 'object') return emptyLayout();
  const raw = input as Partial<LayoutData>;
  return withIds({
    ...raw,
    version: Number(raw.version || 1),
    items: Array.isArray(raw.items) ? raw.items : [],
  } as LayoutData);
}

export function createFurniture(furnitureType: string, x = 0, z = 0): LayoutItem {
  const spec = FURNITURE[furnitureType] || FURNITURE.sofa_3;
  return {
    id: crypto.randomUUID?.() || `item-${Date.now().toString(16)}`,
    type: 'furniture',
    furnitureType,
    name: spec.label,
    pos: [x, spec.geo[1] / 2, z],
    geo: [...spec.geo],
    rot: 0,
    color: spec.color,
    visible: true,
  };
}

export function createWallBetween(a: { x: number; z: number }, b: { x: number; z: number }, height = 2.6): LayoutItem {
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const length = Math.max(0.05, Math.hypot(dx, dz));
  return {
    id: crypto.randomUUID?.() || `wall-${Date.now().toString(16)}`,
    type: 'wall',
    name: 'Wall',
    pos: [(a.x + b.x) / 2, height / 2, (a.z + b.z) / 2],
    geo: [length, height, 0.15],
    rot: Math.atan2(dz, dx),
    color: 0x9aa4a8,
    visible: true,
  };
}

export function roomLayout(width = 3.6, depth = 3.2, height = 2.6): LayoutData {
  const hw = width / 2;
  const hd = depth / 2;
  return withIds({
    ...emptyLayout(),
    metadata: { source_type: 'manual', width_m: width, depth_m: depth, height_m: height },
    rooms: [{ id: 'room-1', label: 'Room', polygon: [{ x: -hw, z: -hd }, { x: hw, z: -hd }, { x: hw, z: hd }, { x: -hw, z: hd }] }],
    items: [
      createWallBetween({ x: -hw, z: -hd }, { x: hw, z: -hd }, height),
      createWallBetween({ x: hw, z: -hd }, { x: hw, z: hd }, height),
      createWallBetween({ x: hw, z: hd }, { x: -hw, z: hd }, height),
      createWallBetween({ x: -hw, z: hd }, { x: -hw, z: -hd }, height),
    ],
  });
}

export function sampleLayouts(): Record<string, LayoutData> {
  const compact = roomLayout(4.2, 3.4);
  compact.items.push(createFurniture('sofa_3', -0.7, 0.8), createFurniture('desk', 1.0, -0.8));
  compact.items = compact.items.map((item) => ({ ...item, id: item.id || crypto.randomUUID?.() || `item-${Math.random()}` }));
  const bedroom = roomLayout(3.2, 3.0);
  bedroom.items.push(createFurniture('bed_queen', -0.5, 0.2), createFurniture('wardrobe', 1.1, -0.9));
  return {
    compact,
    bedroom,
    blank: emptyLayout(),
  };
}

export function layoutToSvg(layout: LayoutData): string {
  const items = layout.items || [];
  const xs = items.flatMap((item) => [item.pos[0] - item.geo[0] / 2, item.pos[0] + item.geo[0] / 2]);
  const zs = items.flatMap((item) => [item.pos[2] - item.geo[2] / 2, item.pos[2] + item.geo[2] / 2]);
  const minX = Math.min(-3, ...xs);
  const maxX = Math.max(3, ...xs);
  const minZ = Math.min(-3, ...zs);
  const maxZ = Math.max(3, ...zs);
  const scale = 80;
  const width = Math.ceil((maxX - minX) * scale + 40);
  const height = Math.ceil((maxZ - minZ) * scale + 40);
  const rects = items.map((item) => {
    const w = item.geo[0] * scale;
    const h = item.geo[2] * scale;
    const x = (item.pos[0] - item.geo[0] / 2 - minX) * scale + 20;
    const y = (item.pos[2] - item.geo[2] / 2 - minZ) * scale + 20;
    const fill = `#${(item.color || 0x9aa4a8).toString(16).padStart(6, '0')}`;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${fill}" stroke="#111" stroke-width="1" transform="rotate(${((item.rot || 0) * 180 / Math.PI).toFixed(1)} ${(x + w / 2).toFixed(1)} ${(y + h / 2).toFixed(1)})"><title>${item.name || item.type}</title></rect>`;
  }).join('\n');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">\n<rect width="100%" height="100%" fill="#f8fafc"/>\n${rects}\n</svg>`;
}
