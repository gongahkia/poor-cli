import { isTauriRuntime } from '@/lib/runtime';

type DirEntry = { name?: string };

interface TauriFsModule {
  mkdir: (path: string, options?: { recursive?: boolean }) => Promise<void>;
  readTextFile: (path: string) => Promise<string>;
  writeTextFile: (path: string, contents: string) => Promise<void>;
  readDir: (path: string) => Promise<DirEntry[]>;
  remove: (path: string) => Promise<void>;
  exists: (path: string) => Promise<boolean>;
}

interface TauriPathModule {
  appDataDir: () => Promise<string>;
}

const WEB_STORAGE_KEYS = {
  settings: 'junas_web_settings',
  profiles: 'junas_web_profiles',
  snippets: 'junas_web_snippets',
  errorEvents: 'junas_web_observability_errors',
  conversationsIndex: 'junas_web_conversation_ids',
  conversationPrefix: 'junas_web_conversation_',
} as const;

const memoryStorage = new Map<string, string>();

let basePath: string | null = null;
let fsModuleCache: TauriFsModule | null = null;
let pathModuleCache: TauriPathModule | null = null;

function getConversationStorageKey(id: string): string {
  return `${WEB_STORAGE_KEYS.conversationPrefix}${id}`;
}

function storageGetItem(key: string): string | null {
  if (typeof window !== 'undefined') return localStorage.getItem(key);
  return memoryStorage.get(key) ?? null;
}

function storageSetItem(key: string, value: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem(key, value);
    return;
  }
  memoryStorage.set(key, value);
}

function storageRemoveItem(key: string): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(key);
    return;
  }
  memoryStorage.delete(key);
}

function readWebJson<T>(key: string, fallback: T): T {
  try {
    const raw = storageGetItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeWebJson(key: string, data: unknown): void {
  storageSetItem(key, JSON.stringify(data));
}

function getWebConversationIds(): string[] {
  return readWebJson<string[]>(WEB_STORAGE_KEYS.conversationsIndex, []);
}

function setWebConversationIds(ids: string[]): void {
  writeWebJson(WEB_STORAGE_KEYS.conversationsIndex, Array.from(new Set(ids)));
}

async function getTauriFs(): Promise<TauriFsModule | null> {
  if (!isTauriRuntime()) return null;
  if (fsModuleCache) return fsModuleCache;
  const module = await import('@tauri-apps/plugin-fs');
  fsModuleCache = module as TauriFsModule;
  return fsModuleCache;
}

async function getTauriPath(): Promise<TauriPathModule | null> {
  if (!isTauriRuntime()) return null;
  if (pathModuleCache) return pathModuleCache;
  const module = await import('@tauri-apps/api/path');
  pathModuleCache = module as TauriPathModule;
  return pathModuleCache;
}

async function getBasePath(): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  if (!basePath) {
    const pathModule = await getTauriPath();
    if (!pathModule) return null;
    basePath = await pathModule.appDataDir();
  }
  return basePath;
}

async function ensureDir(path: string): Promise<void> {
  const fs = await getTauriFs();
  if (!fs) return;
  if (!(await fs.exists(path))) await fs.mkdir(path, { recursive: true });
}

async function readJson<T>(path: string, fallback: T): Promise<T> {
  const fs = await getTauriFs();
  if (!fs) return fallback;
  try {
    if (!(await fs.exists(path))) return fallback;
    const text = await fs.readTextFile(path);
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

async function writeJson(path: string, data: unknown): Promise<void> {
  const fs = await getTauriFs();
  if (!fs) return;
  await fs.writeTextFile(path, JSON.stringify(data, null, 2));
}

// task 35: save conversation
export async function saveConversation(id: string, data: unknown): Promise<void> {
  if (!isTauriRuntime()) {
    writeWebJson(getConversationStorageKey(id), data);
    setWebConversationIds([...getWebConversationIds(), id]);
    return;
  }

  const base = await getBasePath();
  if (!base) return;
  const dir = `${base}/conversations`;
  await ensureDir(dir);
  await writeJson(`${dir}/${id}.json`, data);
}

// task 36: load conversation
export async function loadConversation(id: string): Promise<unknown | null> {
  if (!isTauriRuntime()) {
    return readWebJson<unknown | null>(getConversationStorageKey(id), null);
  }

  const base = await getBasePath();
  if (!base) return null;
  return readJson(`${base}/conversations/${id}.json`, null);
}

// task 37: list conversations
export async function listConversations(): Promise<
  { id: string; name: string; updatedAt: string }[]
> {
  if (!isTauriRuntime()) {
    const ids = getWebConversationIds();
    return ids
      .map((id) => {
        const data = readWebJson<Record<string, unknown> | null>(getConversationStorageKey(id), null);
        if (!data) return null;
        return {
          id,
          name:
            typeof data.title === 'string'
              ? data.title
              : typeof data.name === 'string'
                ? data.name
                : id,
          updatedAt: typeof data.updatedAt === 'string' ? data.updatedAt : '',
        };
      })
      .filter((item): item is { id: string; name: string; updatedAt: string } => item !== null);
  }

  const fs = await getTauriFs();
  const base = await getBasePath();
  if (!fs || !base) return [];

  const dir = `${base}/conversations`;
  await ensureDir(dir);
  try {
    const entries = await fs.readDir(dir);
    const results: { id: string; name: string; updatedAt: string }[] = [];
    for (const entry of entries) {
      if (entry.name?.endsWith('.json')) {
        const id = entry.name.replace('.json', '');
        const data = await readJson<Record<string, unknown> | null>(`${dir}/${entry.name}`, null);
        if (data) {
          results.push({
            id,
            name:
              typeof data.title === 'string'
                ? data.title
                : typeof data.name === 'string'
                  ? data.name
                  : id,
            updatedAt: typeof data.updatedAt === 'string' ? data.updatedAt : '',
          });
        }
      }
    }
    return results;
  } catch {
    return [];
  }
}

// task 38: delete conversation
export async function deleteConversation(id: string): Promise<void> {
  if (!isTauriRuntime()) {
    storageRemoveItem(getConversationStorageKey(id));
    setWebConversationIds(getWebConversationIds().filter((item) => item !== id));
    return;
  }

  const fs = await getTauriFs();
  const base = await getBasePath();
  if (!fs || !base) return;
  const path = `${base}/conversations/${id}.json`;
  if (await fs.exists(path)) await fs.remove(path);
}

// task 39: save settings
export async function saveSettings(settings: unknown): Promise<void> {
  if (!isTauriRuntime()) {
    writeWebJson(WEB_STORAGE_KEYS.settings, settings);
    return;
  }

  const base = await getBasePath();
  if (!base) return;
  await ensureDir(base);
  await writeJson(`${base}/settings.json`, settings);
}

// task 40: load settings
export async function loadSettings<T>(defaults: T): Promise<T> {
  if (!isTauriRuntime()) {
    return readWebJson<T>(WEB_STORAGE_KEYS.settings, defaults);
  }

  const base = await getBasePath();
  if (!base) return defaults;
  return readJson<T>(`${base}/settings.json`, defaults);
}

// task 41: profiles
export async function saveProfiles(profiles: unknown): Promise<void> {
  if (!isTauriRuntime()) {
    writeWebJson(WEB_STORAGE_KEYS.profiles, profiles);
    return;
  }

  const base = await getBasePath();
  if (!base) return;
  await ensureDir(base);
  await writeJson(`${base}/profiles.json`, profiles);
}

export async function loadProfiles<T>(defaults: T): Promise<T> {
  if (!isTauriRuntime()) {
    return readWebJson<T>(WEB_STORAGE_KEYS.profiles, defaults);
  }

  const base = await getBasePath();
  if (!base) return defaults;
  return readJson<T>(`${base}/profiles.json`, defaults);
}

// task 42: snippets
export async function saveSnippets(snippets: unknown): Promise<void> {
  if (!isTauriRuntime()) {
    writeWebJson(WEB_STORAGE_KEYS.snippets, snippets);
    return;
  }

  const base = await getBasePath();
  if (!base) return;
  await ensureDir(base);
  await writeJson(`${base}/snippets.json`, snippets);
}

export async function loadSnippets<T>(defaults: T): Promise<T> {
  if (!isTauriRuntime()) {
    return readWebJson<T>(WEB_STORAGE_KEYS.snippets, defaults);
  }

  const base = await getBasePath();
  if (!base) return defaults;
  return readJson<T>(`${base}/snippets.json`, defaults);
}

// local observability errors
export async function saveErrorEvents(events: unknown): Promise<void> {
  if (!isTauriRuntime()) {
    writeWebJson(WEB_STORAGE_KEYS.errorEvents, events);
    return;
  }

  const base = await getBasePath();
  if (!base) return;
  await ensureDir(base);
  await writeJson(`${base}/observability-errors.json`, events);
}

export async function loadErrorEvents<T>(defaults: T): Promise<T> {
  if (!isTauriRuntime()) {
    return readWebJson<T>(WEB_STORAGE_KEYS.errorEvents, defaults);
  }

  const base = await getBasePath();
  if (!base) return defaults;
  return readJson<T>(`${base}/observability-errors.json`, defaults);
}
