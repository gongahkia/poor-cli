import type { ModelDef } from "./model-registry";
import { LOCAL_MODELS } from "./model-registry";

const CACHE_NAME = "junas-models-v1";
const META_KEY = "junas_local_models_meta";

export interface ModelMeta {
  id: string;
  downloadedAt: number;
  sizeBytes: number;
}

function getMeta(): Record<string, ModelMeta> {
  try { return JSON.parse(localStorage.getItem(META_KEY) || "{}"); }
  catch { return {}; }
}
function saveMeta(meta: Record<string, ModelMeta>) {
  localStorage.setItem(META_KEY, JSON.stringify(meta));
}

export function isModelDownloaded(modelId: string): boolean {
  return !!getMeta()[modelId];
}

export function getModelMeta(modelId: string): ModelMeta | null {
  return getMeta()[modelId] || null;
}

export function getAllModelStatus(): { model: ModelDef; meta: ModelMeta | null }[] {
  const meta = getMeta();
  return LOCAL_MODELS.map(m => ({ model: m, meta: meta[m.id] || null }));
}

export async function downloadModel(
  model: ModelDef,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  const cache = await caches.open(CACHE_NAME);
  // download model ONNX
  const modelResp = await fetch(model.modelUrl, { signal });
  if (!modelResp.ok) throw new Error(`HTTP ${modelResp.status} downloading ${model.name}`);
  const total = parseInt(modelResp.headers.get("content-length") || "0") || model.sizeBytes;
  const reader = modelResp.body!.getReader();
  const chunks: BlobPart[] = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    onProgress(Math.min(received / total, 0.95)); // reserve 5% for tokenizer
  }
  const blob = new Blob(chunks);
  await cache.put(model.modelUrl, new Response(blob, { headers: { "Content-Type": "application/octet-stream" } }));
  // download tokenizer
  const tokResp = await fetch(model.tokenizerUrl, { signal });
  if (!tokResp.ok) throw new Error(`HTTP ${tokResp.status} downloading tokenizer for ${model.name}`);
  const tokBlob = await tokResp.blob();
  await cache.put(model.tokenizerUrl, new Response(tokBlob, { headers: { "Content-Type": "application/json" } }));
  onProgress(1);
  // save metadata
  const meta = getMeta();
  meta[model.id] = { id: model.id, downloadedAt: Date.now(), sizeBytes: received + tokBlob.size };
  saveMeta(meta);
}

export async function deleteModel(modelId: string): Promise<void> {
  const model = LOCAL_MODELS.find(m => m.id === modelId);
  if (!model) return;
  const cache = await caches.open(CACHE_NAME);
  await cache.delete(model.modelUrl);
  await cache.delete(model.tokenizerUrl);
  const meta = getMeta();
  delete meta[modelId];
  saveMeta(meta);
}

export async function deleteAllModels(): Promise<void> {
  await caches.delete(CACHE_NAME);
  saveMeta({});
}

export async function getModelBlob(model: ModelDef): Promise<ArrayBuffer | null> {
  const cache = await caches.open(CACHE_NAME);
  const resp = await cache.match(model.modelUrl);
  if (!resp) return null;
  return resp.arrayBuffer();
}

export async function getTokenizerJson(model: ModelDef): Promise<any | null> {
  const cache = await caches.open(CACHE_NAME);
  const resp = await cache.match(model.tokenizerUrl);
  if (!resp) return null;
  return resp.json();
}

export function clearAllSiteData() {
  localStorage.clear();
  caches.keys().then(names => names.forEach(n => caches.delete(n)));
}
