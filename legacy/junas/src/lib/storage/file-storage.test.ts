import { beforeEach, describe, expect, it, vi } from 'vitest';

const files = new Map<string, string>();
const dirs = new Set<string>();

function normalize(path: string): string {
  return path.replace(/\/+/g, '/').replace(/\/$/, '') || '/';
}

function ensureDir(path: string) {
  const normalized = normalize(path);
  dirs.add(normalized);
}

function ensureParents(path: string) {
  const normalized = normalize(path);
  const parts = normalized.split('/').filter(Boolean);
  let current = '';

  for (let i = 0; i < parts.length - 1; i += 1) {
    current += `/${parts[i]}`;
    ensureDir(current);
  }
}

vi.mock('@tauri-apps/api/path', () => ({
  appDataDir: vi.fn(async () => '/app-data'),
}));

vi.mock('@tauri-apps/plugin-fs', () => ({
  mkdir: vi.fn(async (path: string) => {
    ensureDir(path);
  }),
  readTextFile: vi.fn(async (path: string) => {
    const key = normalize(path);
    const text = files.get(key);
    if (text === undefined) throw new Error(`File not found: ${key}`);
    return text;
  }),
  writeTextFile: vi.fn(async (path: string, text: string) => {
    const key = normalize(path);
    ensureParents(key);
    files.set(key, text);
  }),
  readDir: vi.fn(async (path: string) => {
    const prefix = `${normalize(path)}/`;
    const names = new Set<string>();

    for (const key of files.keys()) {
      if (!key.startsWith(prefix)) continue;
      const remainder = key.slice(prefix.length);
      if (!remainder || remainder.includes('/')) continue;
      names.add(remainder);
    }

    return Array.from(names).map((name) => ({ name }));
  }),
  remove: vi.fn(async (path: string) => {
    files.delete(normalize(path));
  }),
  exists: vi.fn(async (path: string) => {
    const key = normalize(path);
    if (files.has(key) || dirs.has(key)) return true;
    const withSlash = `${key}/`;
    for (const file of files.keys()) {
      if (file.startsWith(withSlash)) return true;
    }
    return false;
  }),
}));

import * as storage from '@/lib/storage/file-storage';

describe('file-storage conversation persistence', () => {
  beforeEach(() => {
    files.clear();
    dirs.clear();
  });

  it('round-trips a conversation payload', async () => {
    const payload = {
      id: 'conv-1',
      title: 'Contract Review',
      messages: [{ id: 'm1', role: 'user', content: 'Hello' }],
      updatedAt: '2026-02-28T00:00:00.000Z',
    };

    await storage.saveConversation('conv-1', payload);
    const loaded = await storage.loadConversation('conv-1');

    expect(loaded).toEqual(payload);
  });

  it('lists saved conversation metadata', async () => {
    await storage.saveConversation('conv-1', {
      title: 'Due Diligence',
      updatedAt: '2026-02-28T01:00:00.000Z',
    });

    const list = await storage.listConversations();

    expect(list).toEqual([
      {
        id: 'conv-1',
        name: 'Due Diligence',
        updatedAt: '2026-02-28T01:00:00.000Z',
      },
    ]);
  });
});
