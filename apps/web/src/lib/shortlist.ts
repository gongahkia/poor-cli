import type { ShortlistEntry } from "@/types/bulk";

const SHORTLIST_KEY = "dude.localShortlist.v1";

const readEntries = (): ShortlistEntry[] => {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SHORTLIST_KEY) ?? "[]") as unknown;
    return Array.isArray(parsed)
      ? parsed.filter((item): item is ShortlistEntry =>
          item !== null
          && typeof item === "object"
          && !Array.isArray(item)
          && typeof (item as ShortlistEntry).canonicalIdentifier === "string",
        )
      : [];
  } catch {
    return [];
  }
};

const writeEntries = (entries: readonly ShortlistEntry[]): void => {
  window.localStorage.setItem(SHORTLIST_KEY, JSON.stringify(entries));
  window.dispatchEvent(new Event("dude-shortlist-change"));
};

export const getShortlist = (): ShortlistEntry[] => readEntries();

export const isShortlisted = (identifier: string, entries = readEntries()): boolean =>
  entries.some((entry) => entry.canonicalIdentifier.toUpperCase() === identifier.toUpperCase());

export const saveShortlistEntry = (entry: ShortlistEntry): ShortlistEntry[] => {
  const entries = readEntries().filter(
    (item) => item.canonicalIdentifier.toUpperCase() !== entry.canonicalIdentifier.toUpperCase(),
  );
  const nextEntries = [{ ...entry, savedAt: new Date().toISOString() }, ...entries].slice(0, 100);
  writeEntries(nextEntries);
  return nextEntries;
};

export const removeShortlistEntry = (identifier: string): ShortlistEntry[] => {
  const nextEntries = readEntries().filter(
    (entry) => entry.canonicalIdentifier.toUpperCase() !== identifier.toUpperCase(),
  );
  writeEntries(nextEntries);
  return nextEntries;
};

export const clearShortlist = (): ShortlistEntry[] => {
  writeEntries([]);
  return [];
};
