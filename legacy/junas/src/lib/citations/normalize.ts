import type { ExtractedCitation } from './extract';

export interface NormalizedCitation extends ExtractedCitation {
  normalizedText: string;
}

function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function normalizeCapNumber(capNumber: string): string {
  const withoutPrefix = compactWhitespace(capNumber).replace(/^Cap\.?\s*/i, '');
  const normalizedRevEd = withoutPrefix.replace(/(\d{4})\s+rev\.?\s*ed/gi, '$1 Rev Ed');
  return `Cap. ${normalizedRevEd}`;
}

function normalizeStatuteName(name: string): string {
  return compactWhitespace(name);
}

export function normalizeExtractedCitation(citation: ExtractedCitation): NormalizedCitation {
  switch (citation.kind) {
    case 'slr_r':
      if (
        typeof citation.year === 'number' &&
        typeof citation.volume === 'number' &&
        typeof citation.pageOrDecision === 'number'
      ) {
        return {
          ...citation,
          normalizedText: `[${citation.year}] ${citation.volume} SLR(R) ${citation.pageOrDecision}`,
        };
      }
      return { ...citation, normalizedText: compactWhitespace(citation.text) };

    case 'slr':
      if (
        typeof citation.year === 'number' &&
        typeof citation.volume === 'number' &&
        typeof citation.pageOrDecision === 'number'
      ) {
        return {
          ...citation,
          normalizedText: `[${citation.year}] ${citation.volume} SLR ${citation.pageOrDecision}`,
        };
      }
      return { ...citation, normalizedText: compactWhitespace(citation.text) };

    case 'sgca':
      if (typeof citation.year === 'number' && typeof citation.pageOrDecision === 'number') {
        return {
          ...citation,
          normalizedText: `[${citation.year}] SGCA ${citation.pageOrDecision}`,
        };
      }
      return {
        ...citation,
        normalizedText: compactWhitespace(citation.text).replace(/\bsgca\b/gi, 'SGCA'),
      };

    case 'sghc':
      if (typeof citation.year === 'number' && typeof citation.pageOrDecision === 'number') {
        return {
          ...citation,
          normalizedText: `[${citation.year}] SGHC ${citation.pageOrDecision}`,
        };
      }
      return {
        ...citation,
        normalizedText: compactWhitespace(citation.text).replace(/\bsghc\b/gi, 'SGHC'),
      };

    case 'statute_cap': {
      const statuteName = normalizeStatuteName(citation.statuteName || citation.text);
      const capNumber = normalizeCapNumber(citation.capNumber || '');
      return {
        ...citation,
        normalizedText: `${statuteName} (${capNumber})`,
      };
    }

    default:
      return { ...citation, normalizedText: compactWhitespace(citation.text) };
  }
}

export function normalizeExtractedCitations(citations: ExtractedCitation[]): NormalizedCitation[] {
  return citations.map((citation) => normalizeExtractedCitation(citation));
}
