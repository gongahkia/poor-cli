export type SingaporeCitationKind = 'slr_r' | 'slr' | 'sgca' | 'sghc' | 'statute_cap';
export type MalaysiaCitationKind = 'mlj' | 'mlju' | 'mlra' | 'clj' | 'my_statute';
export type CitationKind = SingaporeCitationKind | MalaysiaCitationKind;

export interface ExtractedCitation {
  kind: CitationKind;
  text: string;
  start: number;
  end: number;
  year?: number;
  volume?: number;
  pageOrDecision?: number;
  statuteName?: string;
  capNumber?: string;
}

interface CitationPattern {
  kind: CitationKind;
  regex: RegExp;
  map: (match: RegExpMatchArray, start: number) => ExtractedCitation | null;
}

const CITATION_PATTERNS: CitationPattern[] = [
  {
    kind: 'slr_r',
    regex: /\[(\d{4})\]\s+(\d+)\s+SLR\(R\)\s+(\d+)/g,
    map: (match, start) => ({
      kind: 'slr_r',
      text: match[0],
      start,
      end: start + match[0].length,
      year: Number(match[1]),
      volume: Number(match[2]),
      pageOrDecision: Number(match[3]),
    }),
  },
  {
    kind: 'slr',
    regex: /\[(\d{4})\]\s+(\d+)\s+SLR\s+(\d+)/g,
    map: (match, start) => ({
      kind: 'slr',
      text: match[0],
      start,
      end: start + match[0].length,
      year: Number(match[1]),
      volume: Number(match[2]),
      pageOrDecision: Number(match[3]),
    }),
  },
  {
    kind: 'sgca',
    regex: /\[(\d{4})\]\s+SGCA\s+(\d+)/g,
    map: (match, start) => ({
      kind: 'sgca',
      text: match[0],
      start,
      end: start + match[0].length,
      year: Number(match[1]),
      pageOrDecision: Number(match[2]),
    }),
  },
  {
    kind: 'sghc',
    regex: /\[(\d{4})\]\s+SGHC\s+(\d+)/g,
    map: (match, start) => ({
      kind: 'sghc',
      text: match[0],
      start,
      end: start + match[0].length,
      year: Number(match[1]),
      pageOrDecision: Number(match[2]),
    }),
  },
  {
    kind: 'statute_cap',
    regex:
      /\b([A-Z][A-Za-z0-9&'/-]*(?:\s+[A-Z][A-Za-z0-9&'/-]*)*\s+Act)\s*\((Cap\.?\s*[0-9A-Z]+(?:\s*,\s*\d{4}\s+Rev\s+Ed)?)\)/g,
    map: (match, start) => ({
      kind: 'statute_cap',
      text: match[0],
      start,
      end: start + match[0].length,
      statuteName: match[1],
      capNumber: match[2].replace(/\s+/g, ' ').trim(),
    }),
  },
];

function dedupeCitationMatches(citations: ExtractedCitation[]): ExtractedCitation[] {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = `${citation.kind}:${citation.start}:${citation.end}:${citation.text}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function extractSingaporeCitations(text: string): ExtractedCitation[] {
  if (!text) return [];

  const matches: ExtractedCitation[] = [];

  CITATION_PATTERNS.forEach((pattern) => {
    let match: RegExpExecArray | null = pattern.regex.exec(text);
    while (match) {
      const mapped = pattern.map(match, match.index);
      if (mapped) {
        matches.push(mapped);
      }
      match = pattern.regex.exec(text);
    }
    pattern.regex.lastIndex = 0;
  });

  return dedupeCitationMatches(matches).sort((a, b) => a.start - b.start);
}
