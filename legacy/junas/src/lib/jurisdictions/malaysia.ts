import type { JurisdictionConfig } from './jurisdiction';

export const MALAYSIA: JurisdictionConfig = {
  id: 'my',
  name: 'Malaysia',
  shortName: 'MY',
  citationPatterns: [
    {
      kind: 'mlj',
      regex: /\[(\d{4})\]\s+(\d+)\s+MLJ\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'mlj', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), volume: Number(match[2]), pageOrDecision: Number(match[3]),
      }),
    },
    {
      kind: 'mlju',
      regex: /\[(\d{4})\]\s+MLJU\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'mlju', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), pageOrDecision: Number(match[2]),
      }),
    },
    {
      kind: 'mlra',
      regex: /\[(\d{4})\]\s+MLRA\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'mlra', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), pageOrDecision: Number(match[2]),
      }),
    },
    {
      kind: 'clj',
      regex: /\[(\d{4})\]\s+(\d+)\s+CLJ\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'clj', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), volume: Number(match[2]), pageOrDecision: Number(match[3]),
      }),
    },
    {
      kind: 'my_statute',
      regex: /\b([A-Z][A-Za-z0-9&'/-]*(?:\s+[A-Z][A-Za-z0-9&'/-]*)*\s+Act)\s+(\d{4})/g,
      map: (match, start) => ({
        kind: 'my_statute', text: match[0], start, end: start + match[0].length,
        statuteName: match[1], year: Number(match[2]),
      }),
    },
  ],
  legalSourceDomains: {
    caseLaw: ['commonlii.org/my', 'kehakiman.gov.my'],
    statutes: ['lom.agc.gov.my', 'commonlii.org/my'],
  },
  systemPromptAddition: `You are specialized in Malaysian law. Use proper Malaysian citation formats:
- [YYYY] X MLJ XXX (Malayan Law Journal)
- [YYYY] MLJU XX (MLJ Unreported)
- [YYYY] X CLJ XXX (Current Law Journal)
- Statute format: Act Name YYYY (e.g., Contracts Act 1950)`,
  templateIds: [],
};
