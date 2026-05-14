type WorkerTaskCommand = 'extract-entities' | 'analyze-document';

interface WorkerRequest {
  id: string;
  command: WorkerTaskCommand;
  text: string;
}

interface WorkerProgressMessage {
  id: string;
  type: 'progress';
  content: string;
}

interface WorkerResultMessage {
  id: string;
  type: 'result';
  content: string;
}

interface WorkerErrorMessage {
  id: string;
  type: 'error';
  error: string;
}

type WorkerResponse = WorkerProgressMessage | WorkerResultMessage | WorkerErrorMessage;

interface PendingTask {
  resolve: (value: string) => void;
  reject: (error: Error) => void;
  onProgress?: (content: string) => void;
}

let worker: Worker | null = null;
const pendingTasks = new Map<string, PendingTask>();

function createId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `nlp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function ensureWorker(): Worker {
  if (worker) return worker;

  worker = new Worker(new URL('./nlp-worker.ts', import.meta.url), { type: 'module' });
  worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
    const payload = event.data;
    const task = pendingTasks.get(payload.id);
    if (!task) return;

    if (payload.type === 'progress') {
      task.onProgress?.(payload.content);
      return;
    }

    pendingTasks.delete(payload.id);
    if (payload.type === 'result') {
      task.resolve(payload.content);
      return;
    }

    task.reject(new Error(payload.error));
  };

  worker.onerror = (event) => {
    const errorMessage = event.message || 'NLP worker crashed.';
    pendingTasks.forEach((task) => task.reject(new Error(errorMessage)));
    pendingTasks.clear();
    worker = null;
  };

  return worker;
}

export async function runNlpWorkerTask(
  command: WorkerTaskCommand,
  text: string,
  onProgress?: (content: string) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const id = createId();
    pendingTasks.set(id, { resolve, reject, onProgress });
    const request: WorkerRequest = { id, command, text };
    ensureWorker().postMessage(request);
  });
}
