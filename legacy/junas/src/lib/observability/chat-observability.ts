import { loadErrorEvents, saveErrorEvents } from '@/lib/storage/file-storage';

export type ObservabilityChannel = 'provider' | 'tool';

export interface ChatObservabilityEvent {
  id: string;
  channel: ObservabilityChannel;
  name: string;
  operation: string;
  durationMs: number;
  success: boolean;
  failureRate: number;
  averageDurationMs: number;
  timestamp: string;
  error?: string;
}

interface MetricAccumulator {
  total: number;
  failures: number;
  totalDurationMs: number;
}

const EVENT_NAME = 'junas-observability';
const MAX_RECENT_EVENTS = 200;
const MAX_PERSISTED_ERROR_EVENTS = 200;
const recentEvents: ChatObservabilityEvent[] = [];
const metricAccumulators = new Map<string, MetricAccumulator>();
let persistedErrorEvents: ChatObservabilityEvent[] = [];
let hasLoadedPersistedErrors = false;
let pendingPersistFlush: ReturnType<typeof setTimeout> | null = null;

function createEventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `obs-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function metricKey(channel: ObservabilityChannel, name: string, operation: string): string {
  return `${channel}:${name}:${operation}`;
}

function updateMetricAccumulator(
  channel: ObservabilityChannel,
  name: string,
  operation: string,
  durationMs: number,
  success: boolean
): { failureRate: number; averageDurationMs: number } {
  const key = metricKey(channel, name, operation);
  const current = metricAccumulators.get(key) || { total: 0, failures: 0, totalDurationMs: 0 };
  const updated: MetricAccumulator = {
    total: current.total + 1,
    failures: current.failures + (success ? 0 : 1),
    totalDurationMs: current.totalDurationMs + durationMs,
  };
  metricAccumulators.set(key, updated);

  return {
    failureRate: updated.failures / updated.total,
    averageDurationMs: updated.totalDurationMs / updated.total,
  };
}

function emitObservabilityEvent(event: ChatObservabilityEvent): void {
  recentEvents.push(event);
  if (recentEvents.length > MAX_RECENT_EVENTS) {
    recentEvents.splice(0, recentEvents.length - MAX_RECENT_EVENTS);
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(EVENT_NAME, {
        detail: event,
      })
    );
  }
}

async function ensurePersistedErrorsLoaded(): Promise<void> {
  if (hasLoadedPersistedErrors) return;
  hasLoadedPersistedErrors = true;

  try {
    const loaded = await loadErrorEvents<ChatObservabilityEvent[]>([]);
    if (Array.isArray(loaded)) {
      persistedErrorEvents = loaded.slice(-MAX_PERSISTED_ERROR_EVENTS);
    }
  } catch {
    persistedErrorEvents = [];
  }
}

function schedulePersistedErrorFlush(): void {
  if (pendingPersistFlush) return;

  pendingPersistFlush = setTimeout(() => {
    pendingPersistFlush = null;
    const snapshot = [...persistedErrorEvents];
    saveErrorEvents(snapshot).catch(() => {
      // Best effort persistence; failures should not interrupt chat flow.
    });
  }, 200);
}

async function persistErrorEvent(event: ChatObservabilityEvent): Promise<void> {
  await ensurePersistedErrorsLoaded();
  persistedErrorEvents.push(event);
  if (persistedErrorEvents.length > MAX_PERSISTED_ERROR_EVENTS) {
    persistedErrorEvents.splice(0, persistedErrorEvents.length - MAX_PERSISTED_ERROR_EVENTS);
  }
  schedulePersistedErrorFlush();
}

function recordEvent(
  channel: ObservabilityChannel,
  name: string,
  operation: string,
  durationMs: number,
  success: boolean,
  error?: string
): ChatObservabilityEvent {
  const metrics = updateMetricAccumulator(channel, name, operation, durationMs, success);
  const event: ChatObservabilityEvent = {
    id: createEventId(),
    channel,
    name,
    operation,
    durationMs,
    success,
    failureRate: metrics.failureRate,
    averageDurationMs: metrics.averageDurationMs,
    timestamp: new Date().toISOString(),
    error,
  };
  emitObservabilityEvent(event);
  if (!success) {
    void persistErrorEvent(event);
  }
  return event;
}

export function recordProviderObservability(
  provider: string,
  operation: string,
  durationMs: number,
  success: boolean,
  error?: string
): ChatObservabilityEvent {
  return recordEvent('provider', provider, operation, durationMs, success, error);
}

export function recordToolObservability(
  toolId: string,
  durationMs: number,
  success: boolean,
  error?: string
): ChatObservabilityEvent {
  return recordEvent('tool', toolId, 'tool_call', durationMs, success, error);
}

export function getRecentObservabilityEvents(): ChatObservabilityEvent[] {
  return [...recentEvents];
}

export async function getPersistedObservabilityErrors(): Promise<ChatObservabilityEvent[]> {
  await ensurePersistedErrorsLoaded();
  return [...persistedErrorEvents];
}
