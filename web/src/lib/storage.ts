import { deleteDB, openDB, type IDBPDatabase } from 'idb';
import type { LayoutData, ProjectRecord, TranscriptEntry } from './types';
import { emptyLayout, withIds } from './types';

const DB_NAME = 'haus-web';
const DB_VERSION = 1;
const ACTIVE_PROJECT_KEY = 'haus.active_project_id';
const SETTINGS_KEY = 'haus.settings';

type HausDb = IDBPDatabase<{
  projects: {
    key: string;
    value: ProjectRecord;
    indexes: { 'by-updated': string };
  };
}>;

let dbPromise: Promise<HausDb> | null = null;

function db(): Promise<HausDb> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(database) {
        const projects = database.createObjectStore('projects', { keyPath: 'id' });
        projects.createIndex('by-updated', 'updatedAt');
      },
    }) as Promise<HausDb>;
  }
  return dbPromise;
}

export async function listProjects(): Promise<ProjectRecord[]> {
  const database = await db();
  return (await database.getAll('projects')).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function loadProject(id: string): Promise<ProjectRecord | undefined> {
  return (await db()).get('projects', id);
}

export async function saveProject(project: ProjectRecord): Promise<ProjectRecord> {
  const next = { ...project, updatedAt: new Date().toISOString(), layout: withIds(project.layout) };
  await (await db()).put('projects', next);
  localStorage.setItem(ACTIVE_PROJECT_KEY, next.id);
  return next;
}

export async function deleteProject(id: string): Promise<void> {
  await (await db()).delete('projects', id);
  if (localStorage.getItem(ACTIVE_PROJECT_KEY) === id) localStorage.removeItem(ACTIVE_PROJECT_KEY);
}

export async function loadActiveProject(): Promise<ProjectRecord> {
  const active = localStorage.getItem(ACTIVE_PROJECT_KEY);
  if (active) {
    const found = await loadProject(active);
    if (found) return found;
  }
  const existing = await listProjects();
  if (existing[0]) return existing[0];
  const created: ProjectRecord = {
    id: crypto.randomUUID?.() || `project-${Date.now().toString(16)}`,
    title: 'Untitled Haus Project',
    journey: 'blank',
    updatedAt: new Date().toISOString(),
    layout: emptyLayout(),
    transcript: [],
    assets: {},
  };
  return saveProject(created);
}

export async function resetBrowserProjects(): Promise<void> {
  dbPromise = null;
  await deleteDB(DB_NAME);
  localStorage.removeItem(ACTIVE_PROJECT_KEY);
}

export function readSettings<T>(fallback: T): T {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

export function writeSettings(value: Record<string, unknown>): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(value));
}

export function appendTranscript(project: ProjectRecord, entry: Omit<TranscriptEntry, 'at'>): ProjectRecord {
  return {
    ...project,
    transcript: [...project.transcript, { ...entry, at: new Date().toISOString() }].slice(-250),
  };
}

export async function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function compressText(text: string): Promise<Blob> {
  if (!('CompressionStream' in window)) return new Blob([text], { type: 'application/json' });
  const stream = new Blob([text], { type: 'application/json' }).stream().pipeThrough(new CompressionStream('gzip'));
  return new Response(stream).blob();
}

async function decompressBlob(blob: Blob): Promise<string> {
  if (blob.type.includes('gzip') && 'DecompressionStream' in window) {
    const stream = blob.stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).text();
  }
  if (blob.name?.endsWith?.('.gz') && 'DecompressionStream' in window) {
    const stream = blob.stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).text();
  }
  return blob.text();
}

export async function exportProjectPackage(project: ProjectRecord): Promise<void> {
  const text = JSON.stringify({ schema: 'haus.browser_project.v1', project }, null, 2);
  const blob = await compressText(text);
  const ext = blob.type === 'application/json' ? 'json' : 'json.gz';
  downloadBlob(blob, `${project.title.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'haus-project'}.haus.${ext}`);
}

export async function importProjectPackage(file: File): Promise<ProjectRecord> {
  const text = await decompressBlob(file);
  const payload = JSON.parse(text);
  const raw = payload.project || payload;
  if (!raw || typeof raw !== 'object' || !raw.layout) throw new Error('Invalid Haus project package.');
  const project: ProjectRecord = {
    id: raw.id || crypto.randomUUID?.() || `project-${Date.now().toString(16)}`,
    title: raw.title || file.name.replace(/\.(haus\.)?json(\.gz)?$/i, ''),
    journey: raw.journey || 'blank',
    updatedAt: new Date().toISOString(),
    layout: withIds(raw.layout as LayoutData),
    transcript: Array.isArray(raw.transcript) ? raw.transcript : [],
    assets: raw.assets || {},
  };
  return saveProject(project);
}

declare global {
  interface Blob {
    name?: string;
  }
}
