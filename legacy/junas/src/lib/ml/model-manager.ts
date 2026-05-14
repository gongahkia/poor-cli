import * as ml from './tauri-ml-bridge';

export type ModelType =
  | 'summarization'
  | 'ner'
  | 'embeddings'
  | 'text-classification'
  | 'text2text-generation';

export interface ModelInfo {
  id: string;
  name: string;
  type: ModelType;
  modelId: string;
  size: string;
  description: string;
  isDownloaded: boolean;
  isLoading: boolean;
  downloadProgress: number;
}

export interface DownloadProgress {
  modelId: string;
  progress: number;
  loaded: number;
  total: number;
  status: 'downloading' | 'loading' | 'ready' | 'error';
  error?: string;
}

export const AVAILABLE_MODELS: Omit<
  ModelInfo,
  'isDownloaded' | 'isLoading' | 'downloadProgress'
>[] = [
  {
    id: 'chat',
    name: 'Local Chat (LaMini)',
    type: 'text2text-generation',
    modelId: 'LaMini-Flan-T5-248M',
    size: '~250MB',
    description: 'General purpose chat and instruction following',
  },
  {
    id: 'summarization',
    name: 'Summarization',
    type: 'summarization',
    modelId: 'distilbart-cnn-6-6',
    size: '~300MB',
    description: 'Summarize long legal documents into concise summaries',
  },
  {
    id: 'ner',
    name: 'Named Entity Recognition',
    type: 'ner',
    modelId: 'bert-base-NER',
    size: '~400MB',
    description: 'Advanced entity extraction (people, organizations, locations)',
  },
  {
    id: 'embeddings',
    name: 'Text Embeddings',
    type: 'embeddings',
    modelId: 'all-MiniLM-L6-v2',
    size: '~80MB',
    description: 'Generate embeddings for semantic search and similarity',
  },
  {
    id: 'text-classification',
    name: 'Text Classification',
    type: 'text-classification',
    modelId: 'distilbert-base-uncased-finetuned-sst-2-english',
    size: '~250MB',
    description: 'Classify text sentiment and categories',
  },
];

const ONNX_RUNTIME_KEY = 'junas_onnx_runtime_available';
let onnxRuntimeAvailabilityCache: boolean | null = null;
const modelStatusCache = new Map<string, ml.ModelCacheStatus>();

function setOnnxAvailabilityFlag(isAvailable: boolean): void {
  onnxRuntimeAvailabilityCache = isAvailable;
  localStorage.setItem(ONNX_RUNTIME_KEY, isAvailable ? 'true' : 'false');
}

export function getCachedOnnxRuntimeAvailability(): boolean | null {
  if (onnxRuntimeAvailabilityCache !== null) return onnxRuntimeAvailabilityCache;
  const stored = localStorage.getItem(ONNX_RUNTIME_KEY);
  if (stored === 'true') return true;
  if (stored === 'false') return false;
  return null;
}

export async function isOnnxRuntimeAvailable(forceRefresh = false): Promise<boolean> {
  if (!forceRefresh) {
    const cached = getCachedOnnxRuntimeAvailability();
    if (cached !== null) return cached;
  }

  try {
    const available = await ml.isOnnxRuntimeAvailable();
    setOnnxAvailabilityFlag(available);
    return available;
  } catch {
    setOnnxAvailabilityFlag(false);
    return false;
  }
}

async function getVerifiedModelStatus(modelId: string): Promise<ml.ModelCacheStatus> {
  const status = await ml.getModelStatus(modelId);
  modelStatusCache.set(modelId, status);
  return status;
}

function getCachedModelStatus(modelId: string): ml.ModelCacheStatus | null {
  return modelStatusCache.get(modelId) || null;
}

function toModelInfo(
  model: Omit<ModelInfo, 'isDownloaded' | 'isLoading' | 'downloadProgress'>
): ModelInfo {
  const status = getCachedModelStatus(model.id);
  const isDownloaded = status?.exists ?? false;
  return {
    ...model,
    isDownloaded,
    isLoading: false,
    downloadProgress: isDownloaded ? 100 : 0,
  };
}

export async function getDownloadedModels(): Promise<string[]> {
  const statuses = await Promise.all(
    AVAILABLE_MODELS.map(async (model) => {
      try {
        const status = await getVerifiedModelStatus(model.id);
        return { id: model.id, exists: status.exists };
      } catch {
        return { id: model.id, exists: false };
      }
    })
  );
  return statuses.filter((status) => status.exists).map((status) => status.id);
}

export async function removeModelFromDownloaded(modelId: string): Promise<void> {
  await ml.removeModelCache(modelId);
  modelStatusCache.set(modelId, {
    model_type: modelId,
    exists: false,
    file_path: '',
    size_bytes: 0,
    sha256: null,
  });
}

export async function clearAllModels(): Promise<void> {
  await ml.clearModelCache();
  AVAILABLE_MODELS.forEach((model) => {
    modelStatusCache.set(model.id, {
      model_type: model.id,
      exists: false,
      file_path: '',
      size_bytes: 0,
      sha256: null,
    });
  });
}

export async function isModelDownloaded(modelId: string): Promise<boolean> {
  const status = await getVerifiedModelStatus(modelId);
  return status.exists;
}

export async function isModelLoaded(modelId: string): Promise<boolean> {
  return isModelDownloaded(modelId);
}

export async function getModelsWithStatus(): Promise<ModelInfo[]> {
  await Promise.all(
    AVAILABLE_MODELS.map(async (model) => {
      try {
        await getVerifiedModelStatus(model.id);
      } catch {
        // If status check fails, preserve existing cached value or default to not downloaded.
        if (!modelStatusCache.has(model.id)) {
          modelStatusCache.set(model.id, {
            model_type: model.id,
            exists: false,
            file_path: '',
            size_bytes: 0,
            sha256: null,
          });
        }
      }
    })
  );

  return AVAILABLE_MODELS.map(toModelInfo);
}

export async function downloadModel(
  modelId: string,
  onProgress?: (progress: DownloadProgress) => void
): Promise<boolean> {
  const modelInfo = AVAILABLE_MODELS.find((model) => model.id === modelId);
  if (!modelInfo) throw new Error(`Unknown model: ${modelId}`);

  onProgress?.({ modelId, progress: 5, loaded: 0, total: 0, status: 'downloading' });

  try {
    const onnxAvailable = await isOnnxRuntimeAvailable();
    if (!onnxAvailable) {
      throw new Error('ONNX runtime is unavailable on this system.');
    }

    await ml.downloadModel(modelInfo.id);
    onProgress?.({ modelId, progress: 85, loaded: 0, total: 0, status: 'loading' });

    await ml.loadModel(modelInfo.id);
    setOnnxAvailabilityFlag(true);

    await getVerifiedModelStatus(modelInfo.id);
    onProgress?.({ modelId, progress: 100, loaded: 0, total: 0, status: 'ready' });
    return true;
  } catch (error) {
    onProgress?.({
      modelId,
      progress: 0,
      loaded: 0,
      total: 0,
      status: 'error',
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

export async function loadModel(modelId: string): Promise<boolean> {
  const onnxAvailable = await isOnnxRuntimeAvailable();
  if (!onnxAvailable) {
    throw new Error('ONNX runtime is unavailable on this system.');
  }

  await ml.loadModel(modelId);
  setOnnxAvailabilityFlag(true);
  await getVerifiedModelStatus(modelId);
  return true;
}

export async function summarize(text: string, maxLength: number = 150): Promise<string> {
  return ml.runSummarize(text, maxLength);
}

export async function generateText(prompt: string, _maxNewTokens: number = 256): Promise<string> {
  return ml.runSummarize(prompt, _maxNewTokens);
}

export async function extractNamedEntities(text: string) {
  return ml.runNer(text);
}

export async function generateEmbeddings(text: string): Promise<number[]> {
  return ml.runEmbeddings(text);
}

export async function classifyText(text: string) {
  return ml.runClassify(text);
}
