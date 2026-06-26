import type { CatalogItem, ChatResponse, ChatStatus, LayoutData, ToolSpec } from './types';

export const API_BASE = (import.meta.env.VITE_HAUS_API_BASE_URL || '').replace(/\/$/, '');

function apiUrl(path: string): string {
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${clean}`;
}

async function readJson<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body?.error) {
    throw new Error(body?.error || body?.result || `HTTP ${res.status}`);
  }
  return body as T;
}

export async function getHealth(): Promise<Record<string, unknown>> {
  return readJson(await fetch(apiUrl('/api/health')));
}

export async function getChatStatus(): Promise<ChatStatus> {
  return readJson(await fetch(apiUrl('/api/chat/status')));
}

export async function getToolCatalog(): Promise<ToolSpec[]> {
  const body = await readJson<{ tools: ToolSpec[] }>(await fetch(apiUrl('/api/chat/tools')));
  return Array.isArray(body.tools) ? body.tools : [];
}

export async function syncLayout(layout: LayoutData): Promise<void> {
  await readJson(await fetch(apiUrl('/api/sync-layout'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(layout),
  }));
}

export async function sendChat(payload: Record<string, unknown>): Promise<ChatResponse> {
  return readJson(await fetch(apiUrl('/api/chat'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
}

export async function dispatchTool(name: string, args: Record<string, unknown>, webSearchDisabled = false): Promise<ChatResponse> {
  return readJson(await fetch(apiUrl('/api/chat/tools/dispatch'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, arguments: args, web_search_disabled: webSearchDisabled }),
  }));
}

export async function confirmTool(token: string): Promise<ChatResponse> {
  return readJson(await fetch(apiUrl(`/api/tool-confirmations/${encodeURIComponent(token)}/confirm`), { method: 'POST' }));
}

export async function applyPlan(planId: string): Promise<Record<string, unknown>> {
  return readJson(await fetch(apiUrl(`/api/design-plans/${encodeURIComponent(planId)}/apply`), { method: 'POST' }));
}

export async function revisePlan(planId: string, revision: string, webSearchDisabled = false): Promise<Record<string, unknown>> {
  return readJson(await fetch(apiUrl(`/api/design-plans/${encodeURIComponent(planId)}/revise`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ revision, web_search_disabled: webSearchDisabled }),
  }));
}

export async function downloadPlanReport(planId: string): Promise<string> {
  const res = await fetch(apiUrl(`/api/design-plans/${encodeURIComponent(planId)}/report`));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

export async function vectorizeFloorPlan(file: File, scalePx: string, scaleM: string, wallHeight: string, clean: boolean): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.set('file', file);
  if (scalePx && scaleM) {
    const px = Number(scalePx);
    const meters = Number(scaleM);
    if (Number.isFinite(px) && px > 0 && Number.isFinite(meters) && meters > 0) {
      form.set('scale_m_per_px', String(meters / px));
    }
  }
  if (wallHeight) form.set('wall_height_m', wallHeight);
  form.set('clean', clean ? '1' : '0');
  return readJson(await fetch(apiUrl('/api/floorplans/vectorize'), { method: 'POST', body: form }));
}

export async function searchCatalog(query: string, refresh = false): Promise<{ items: CatalogItem[]; catalog?: Record<string, unknown> }> {
  const params = new URLSearchParams({ q: query, refresh: refresh ? '1' : '0' });
  return readJson(await fetch(apiUrl(`/api/catalog/ikea/search?${params}`)));
}

export async function catalogLayoutItem(itemId: string, x = 0, z = 0, rotationDeg = 0): Promise<{ layout_item: Record<string, unknown>; item: CatalogItem }> {
  return readJson(await fetch(apiUrl(`/api/catalog/ikea/items/${encodeURIComponent(itemId)}/layout-item`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ x, z, rotation_deg: rotationDeg }),
  }));
}
