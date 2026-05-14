import { chunkText } from './chunker';
import { isTauriRuntime } from '@/lib/runtime';
import { toErrorWithCode } from '@/lib/tauri-error';

interface VectorEntry {
  chunk_id: string;
  text: string;
  embedding: number[];
}

interface SimilarityResult {
  chunk_id: string;
  text: string;
  score: number;
}

// --- in-memory vector store for web mode ---
const webCollections = new Map<string, VectorEntry[]>();

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}

async function invokeRag<T>(command: string, args: Record<string, unknown>): Promise<T> {
  if (!isTauriRuntime()) {
    throw Object.assign(new Error('RAG Tauri command called in web mode.'), { code: 'UNSUPPORTED_RUNTIME' });
  }
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<T>(command, args);
  } catch (error) {
    throw toErrorWithCode(error);
  }
}

async function embedText(text: string): Promise<number[]> {
  if (!isTauriRuntime()) {
    const { webRunEmbeddings } = await import('@/lib/ml/tauri-ml-bridge');
    return webRunEmbeddings(text);
  }
  return invokeRag<number[]>('run_embeddings', { text });
}

export async function indexDocument(
  collectionName: string,
  text: string,
  onProgress?: (done: number, total: number) => void
): Promise<number> {
  const chunks = chunkText(text, 512, 64, collectionName);
  const entries: VectorEntry[] = [];
  for (let i = 0; i < chunks.length; i += 1) {
    const embedding = await embedText(chunks[i].text);
    entries.push({ chunk_id: chunks[i].id, text: chunks[i].text, embedding });
    onProgress?.(i + 1, chunks.length);
  }
  if (!isTauriRuntime()) {
    const existing = webCollections.get(collectionName) || [];
    webCollections.set(collectionName, [...existing, ...entries]);
    return entries.length;
  }
  return invokeRag<number>('index_document', { collection: collectionName, entries });
}

export async function queryRelevantChunks(
  collectionName: string,
  query: string,
  topK = 5
): Promise<SimilarityResult[]> {
  const queryEmbedding = await embedText(query);
  if (!isTauriRuntime()) {
    const entries = webCollections.get(collectionName) || [];
    const scored = entries.map((e) => ({
      chunk_id: e.chunk_id,
      text: e.text,
      score: cosineSimilarity(queryEmbedding, e.embedding),
    }));
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, topK);
  }
  return invokeRag<SimilarityResult[]>('query_similar', { collection: collectionName, queryEmbedding, topK });
}

export function formatRagContext(results: SimilarityResult[]): string {
  if (results.length === 0) return '';
  const header = '**Reference Material (from uploaded documents):**\n\n';
  const body = results
    .map((result, index) => `[${index + 1}] (relevance: ${(result.score * 100).toFixed(0)}%)\n${result.text}`)
    .join('\n\n');
  return `${header}${body}\n\n---\n\n`;
}

export async function listCollections(): Promise<string[]> {
  if (!isTauriRuntime()) return Array.from(webCollections.keys());
  return invokeRag<string[]>('list_collections', {});
}

export async function deleteCollection(name: string): Promise<boolean> {
  if (!isTauriRuntime()) return webCollections.delete(name);
  return invokeRag<boolean>('delete_collection', { collection: name });
}
