import { toErrorWithCode } from '@/lib/tauri-error';
import { isTauriRuntime } from '@/lib/runtime';

export interface NerEntity {
  entity: string;
  word: string;
  start: number;
  end: number;
  score: number;
}

export interface ClassifyResult {
  label: string;
  score: number;
}

export interface ModelCacheStatus {
  model_type: string;
  exists: boolean;
  file_path: string;
  size_bytes: number;
  sha256?: string | null;
}

async function invokeWithAppError<T>(command: string, args: Record<string, unknown>): Promise<T> {
  if (!isTauriRuntime()) {
    throw Object.assign(new Error(`Command "${command}" requires the Tauri desktop runtime.`), { code: 'UNSUPPORTED_RUNTIME' });
  }
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<T>(command, args);
  } catch (error) {
    throw toErrorWithCode(error);
  }
}

// --- web fallback: NER via compromise ---
async function webRunNer(text: string): Promise<NerEntity[]> {
  const nlp = (await import('compromise')).default;
  const doc = nlp(text);
  const entities: NerEntity[] = [];
  const extract = (tag: string, label: string) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    doc.match(`#${tag}+`).forEach((m: any) => {
      const word = String(m.text());
      const off = m.offset();
      entities.push({ entity: label, word, start: off.start, end: off.start + off.length, score: 0.85 });
    });
  };
  extract('Person', 'PER');
  extract('Organization', 'ORG');
  extract('Place', 'LOC');
  extract('Date', 'DATE');
  return entities;
}

// --- web fallback: extractive summarization ---
function webRunSummarize(text: string, maxLength: number): string {
  const sentences = text.match(/[^.!?\n]+[.!?]?/g) || [text];
  if (sentences.length <= 2) return text.slice(0, maxLength);
  const wordFreq = new Map<string, number>();
  const words = text.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/);
  for (const w of words) { if (w.length > 2) wordFreq.set(w, (wordFreq.get(w) || 0) + 1); }
  const scored = sentences.map((s) => {
    const sw = s.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/);
    const score = sw.reduce((sum, w) => sum + (wordFreq.get(w) || 0), 0) / Math.max(sw.length, 1);
    return { s: s.trim(), score };
  });
  scored.sort((a, b) => b.score - a.score);
  let result = '';
  for (const { s } of scored) {
    if ((result + ' ' + s).trim().length > maxLength) break;
    result += (result ? ' ' : '') + s;
  }
  return result || sentences[0].slice(0, maxLength);
}

// --- web fallback: keyword-based classification ---
function webRunClassify(text: string): ClassifyResult[] {
  const lower = text.toLowerCase();
  const positive = ['good', 'great', 'excellent', 'happy', 'positive', 'wonderful', 'best', 'love', 'agree', 'correct', 'right', 'approved', 'granted'];
  const negative = ['bad', 'terrible', 'wrong', 'fail', 'error', 'denied', 'rejected', 'guilty', 'violation', 'breach', 'dismiss', 'refuse', 'against'];
  let pos = 0, neg = 0;
  for (const w of lower.split(/\s+/)) {
    if (positive.includes(w)) pos++;
    if (negative.includes(w)) neg++;
  }
  const total = pos + neg || 1;
  return [
    { label: 'POSITIVE', score: pos / total || 0.5 },
    { label: 'NEGATIVE', score: neg / total || 0.5 },
  ].sort((a, b) => b.score - a.score);
}

// --- web fallback: hash-based embeddings for basic similarity ---
const EMBED_DIM = 384;
export function webRunEmbeddings(text: string): number[] {
  const vec = new Float64Array(EMBED_DIM);
  const words = text.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/).filter(Boolean);
  for (const w of words) {
    let hash = 0;
    for (let i = 0; i < w.length; i++) hash = ((hash << 5) - hash + w.charCodeAt(i)) | 0;
    const idx = Math.abs(hash) % EMBED_DIM;
    vec[idx] += 1;
    vec[(idx + 1) % EMBED_DIM] += 0.5; // spread to neighbor
  }
  const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0)) || 1;
  return Array.from(vec.map((v) => v / norm));
}

// --- exports: dispatch to Tauri or web fallback ---
export const loadModel = (modelType: string) => {
  if (!isTauriRuntime()) return Promise.resolve(`web-fallback-${modelType}`);
  return invokeWithAppError<string>('load_model', { modelType });
};
export const downloadModel = (modelType: string) => {
  if (!isTauriRuntime()) return Promise.resolve(`web-fallback-${modelType}`);
  return invokeWithAppError<string>('download_model', { modelType });
};
export const getModelStatus = (modelType: string): Promise<ModelCacheStatus> => {
  if (!isTauriRuntime()) return Promise.resolve({ model_type: modelType, exists: true, file_path: 'web-fallback', size_bytes: 0, sha256: null });
  return invokeWithAppError<ModelCacheStatus>('get_model_status', { modelType });
};
export const removeModelCache = (modelType: string) => {
  if (!isTauriRuntime()) return Promise.resolve(true);
  return invokeWithAppError<boolean>('remove_model_cache', { modelType });
};
export const clearModelCache = () => {
  if (!isTauriRuntime()) return Promise.resolve();
  return invokeWithAppError<void>('clear_model_cache', {});
};
export const isOnnxRuntimeAvailable = (): Promise<boolean> => {
  if (!isTauriRuntime()) return Promise.resolve(true); // web fallbacks always available
  return invokeWithAppError<boolean>('is_onnx_runtime_available', {});
};
export const runNer = (text: string): Promise<NerEntity[]> => {
  if (!isTauriRuntime()) return webRunNer(text);
  return invokeWithAppError<NerEntity[]>('run_ner', { text });
};
export const runSummarize = (text: string, maxLength: number): Promise<string> => {
  if (!isTauriRuntime()) return Promise.resolve(webRunSummarize(text, maxLength));
  return invokeWithAppError<string>('run_summarize', { text, maxLength });
};
export const runClassify = (text: string): Promise<ClassifyResult[]> => {
  if (!isTauriRuntime()) return Promise.resolve(webRunClassify(text));
  return invokeWithAppError<ClassifyResult[]>('run_classify', { text });
};
export const runEmbeddings = (text: string): Promise<number[]> => {
  if (!isTauriRuntime()) return Promise.resolve(webRunEmbeddings(text));
  return invokeWithAppError<number[]>('run_embeddings', { text });
};
