const TRAILING_READ_MORE_PATTERN = /\s*(?:\.{3}|…)?\s*Read more\.?$/i;

export const getDisplaySnippet = (snippet: string): string => {
  const trimmed = snippet.trim();
  const cleaned = trimmed.replace(TRAILING_READ_MORE_PATTERN, "").trim();
  return cleaned || trimmed;
};

export const getSiteHost = (url: string): string | null => {
  try {
    const parsed = new URL(url);
    return parsed.hostname;
  } catch {
    return null;
  }
};

export const getSiteLabel = (siteName: string | null, url: string): string => siteName ?? getSiteHost(url) ?? "web";

export const getFaviconUrl = (url: string): string | null => {
  const host = getSiteHost(url);
  return host === null
    ? null
    : `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
};
