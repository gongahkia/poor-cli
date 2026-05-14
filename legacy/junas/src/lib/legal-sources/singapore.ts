export interface LegalSearchResult {
  title: string;
  url: string;
  snippet: string;
}

export type SingaporeLegalSourceMode = 'local-first' | 'provider';

export interface SingaporeLegalSourceConfig {
  mode?: SingaporeLegalSourceMode;
  providerKey?: string;
  caseLawCacheKey?: string;
  statuteCacheKey?: string;
  caseLawDomains?: string[];
  statuteDomains?: string[];
}

interface ProviderClient {
  getApiKey: (provider: string) => Promise<string>;
  webSearch: (query: string, apiKey: string) => Promise<LegalSearchResult[]>;
}

export interface SingaporeLegalSourceAdapter {
  searchCaseLaw: (query: string) => Promise<LegalSearchResult[]>;
  researchStatute: (query: string) => Promise<LegalSearchResult[]>;
}

const DEFAULT_CONFIG: Required<SingaporeLegalSourceConfig> = {
  mode: 'local-first',
  providerKey: 'serper',
  caseLawCacheKey: 'junas_case_law_cache',
  statuteCacheKey: 'junas_statute_cache',
  caseLawDomains: ['judiciary.gov.sg', 'singaporelawwatch.sg'],
  statuteDomains: ['sso.agc.gov.sg', 'agc.gov.sg'],
};

function mergeConfig(config?: SingaporeLegalSourceConfig): Required<SingaporeLegalSourceConfig> {
  return {
    mode: config?.mode ?? DEFAULT_CONFIG.mode,
    providerKey: config?.providerKey ?? DEFAULT_CONFIG.providerKey,
    caseLawCacheKey: config?.caseLawCacheKey ?? DEFAULT_CONFIG.caseLawCacheKey,
    statuteCacheKey: config?.statuteCacheKey ?? DEFAULT_CONFIG.statuteCacheKey,
    caseLawDomains:
      config?.caseLawDomains && config.caseLawDomains.length > 0
        ? config.caseLawDomains
        : DEFAULT_CONFIG.caseLawDomains,
    statuteDomains:
      config?.statuteDomains && config.statuteDomains.length > 0
        ? config.statuteDomains
        : DEFAULT_CONFIG.statuteDomains,
  };
}

function readLocalCache(cacheKey: string, query: string): LegalSearchResult[] {
  if (typeof window === 'undefined') return [];

  try {
    const raw = localStorage.getItem(cacheKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const needle = query.toLowerCase();

    return parsed
      .filter(
        (item) =>
          item &&
          typeof item.title === 'string' &&
          typeof item.url === 'string' &&
          typeof item.snippet === 'string'
      )
      .map((item) => ({
        title: item.title as string,
        url: item.url as string,
        snippet: item.snippet as string,
      }))
      .filter(
        (item) =>
          item.title.toLowerCase().includes(needle) || item.snippet.toLowerCase().includes(needle)
      )
      .slice(0, 10);
  } catch {
    return [];
  }
}

function buildScopedQuery(prefix: string, query: string, domains: string[]): string {
  const domainScope = domains.map((domain) => `site:${domain}`).join(' OR ');
  return `${prefix} ${query} ${domainScope}`.trim();
}

async function getProviderClient(): Promise<ProviderClient> {
  const bridge = await import('@/lib/tauri-bridge');
  return {
    getApiKey: bridge.getApiKey,
    webSearch: bridge.webSearch,
  };
}

async function runProviderSearch(
  query: string,
  scopedPrefix: string,
  domains: string[],
  providerKey: string
): Promise<LegalSearchResult[]> {
  const client = await getProviderClient();
  const apiKey = await client.getApiKey(providerKey);
  const scopedQuery = buildScopedQuery(scopedPrefix, query, domains);
  return client.webSearch(scopedQuery, apiKey);
}

async function searchViaSso(query: string): Promise<LegalSearchResult[]> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    const results = await invoke<Array<{ title: string; url: string; snippet: string }>>('search_sso_statutes', { query });
    return results.map((r) => ({ title: r.title, url: r.url, snippet: r.snippet }));
  } catch { return []; }
}

async function searchViaCommonlii(query: string): Promise<LegalSearchResult[]> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    const results = await invoke<Array<{ title: string; url: string; snippet: string }>>('search_commonlii_cases', { query });
    return results.map((r) => ({ title: r.title, url: r.url, snippet: r.snippet }));
  } catch { return []; }
}

export function createSingaporeLegalSourceAdapter(
  config?: SingaporeLegalSourceConfig
): SingaporeLegalSourceAdapter {
  const resolved = mergeConfig(config);

  return {
    async searchCaseLaw(query: string): Promise<LegalSearchResult[]> {
      // 1. local cache
      if (resolved.mode === 'local-first') {
        const localResults = readLocalCache(resolved.caseLawCacheKey, query);
        if (localResults.length > 0) return localResults;
      }
      // 2. CommonLII direct search
      const commonliiResults = await searchViaCommonlii(query);
      if (commonliiResults.length > 0) return commonliiResults;
      // 3. Serper fallback
      return runProviderSearch(query, 'Singapore case law', resolved.caseLawDomains, resolved.providerKey);
    },

    async researchStatute(query: string): Promise<LegalSearchResult[]> {
      // 1. local cache
      if (resolved.mode === 'local-first') {
        const localResults = readLocalCache(resolved.statuteCacheKey, query);
        if (localResults.length > 0) return localResults;
      }
      // 2. SSO direct search
      const ssoResults = await searchViaSso(query);
      if (ssoResults.length > 0) return ssoResults;
      // 3. Serper fallback
      return runProviderSearch(query, 'Singapore statutes', resolved.statuteDomains, resolved.providerKey);
    },
  };
}

function isStringArray(input: unknown): input is string[] {
  return Array.isArray(input) && input.every((item) => typeof item === 'string');
}

export function loadSingaporeLegalSourceConfigFromStorage(): SingaporeLegalSourceConfig {
  if (typeof window === 'undefined') return {};

  try {
    const raw = localStorage.getItem('junas_legal_source_config');
    if (!raw) return {};

    const parsed = JSON.parse(raw) as Partial<SingaporeLegalSourceConfig>;
    const config: SingaporeLegalSourceConfig = {};

    if (parsed.mode === 'local-first' || parsed.mode === 'provider') {
      config.mode = parsed.mode;
    }
    if (typeof parsed.providerKey === 'string') {
      config.providerKey = parsed.providerKey;
    }
    if (typeof parsed.caseLawCacheKey === 'string') {
      config.caseLawCacheKey = parsed.caseLawCacheKey;
    }
    if (typeof parsed.statuteCacheKey === 'string') {
      config.statuteCacheKey = parsed.statuteCacheKey;
    }
    if (isStringArray(parsed.caseLawDomains)) {
      config.caseLawDomains = parsed.caseLawDomains;
    }
    if (isStringArray(parsed.statuteDomains)) {
      config.statuteDomains = parsed.statuteDomains;
    }

    return config;
  } catch {
    return {};
  }
}
