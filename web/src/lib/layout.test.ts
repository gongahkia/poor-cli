import { describe, expect, it } from 'vitest';
import { createFurniture, createWallBetween, layoutToSvg, normalizeLayout, roomLayout } from './layout';

describe('layout helpers', () => {
  it('normalizes malformed layouts to a safe empty item list', () => {
    const layout = normalizeLayout({ version: 1, items: 'bad' });
    expect(layout.items).toEqual([]);
    expect(layout.schema).toBe('haus.layout.v2');
  });

  it('creates walls and furniture with ids and meter dimensions', () => {
    const wall = createWallBetween({ x: -1, z: 0 }, { x: 1, z: 0 }, 2.6);
    const sofa = createFurniture('sofa_3', 0.5, -0.25);
    expect(wall.id).toBeTruthy();
    expect(wall.geo[0]).toBeCloseTo(2);
    expect(sofa.pos).toEqual([0.5, sofa.geo[1] / 2, -0.25]);
  });

  it('exports a top-down svg from a room layout', () => {
    const svg = layoutToSvg(roomLayout(3, 2));
    expect(svg).toContain('<svg');
    expect(svg).toContain('<rect');
  });
});
