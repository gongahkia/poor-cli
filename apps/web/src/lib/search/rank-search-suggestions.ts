import Fuse from "fuse.js";

export type SearchSuggestion = {
  id: string;
  label: string;
  description?: string;
  aliases?: string[];
};

export function rankSearchSuggestions(
  query: string,
  suggestions: SearchSuggestion[],
  limit = 8,
): SearchSuggestion[] {
  const normalizedQuery = query.trim();
  if (normalizedQuery === "") {
    return suggestions.slice(0, limit);
  }

  const fuse = new Fuse(suggestions, {
    keys: ["label", "description", "aliases"],
    threshold: 0.35,
    includeScore: true,
    ignoreLocation: true,
    minMatchCharLength: 2,
  });

  return fuse.search(normalizedQuery, { limit }).map((result) => result.item);
}
