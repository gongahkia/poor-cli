import type { JurisdictionConfig } from './jurisdiction';

export const SINGAPORE: JurisdictionConfig = {
  id: 'sg',
  name: 'Singapore',
  shortName: 'SG',
  citationPatterns: [
    {
      kind: 'slr_r',
      regex: /\[(\d{4})\]\s+(\d+)\s+SLR\(R\)\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'slr_r', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), volume: Number(match[2]), pageOrDecision: Number(match[3]),
      }),
    },
    {
      kind: 'slr',
      regex: /\[(\d{4})\]\s+(\d+)\s+SLR\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'slr', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), volume: Number(match[2]), pageOrDecision: Number(match[3]),
      }),
    },
    {
      kind: 'sgca',
      regex: /\[(\d{4})\]\s+SGCA\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'sgca', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), pageOrDecision: Number(match[2]),
      }),
    },
    {
      kind: 'sghc',
      regex: /\[(\d{4})\]\s+SGHC\s+(\d+)/g,
      map: (match, start) => ({
        kind: 'sghc', text: match[0], start, end: start + match[0].length,
        year: Number(match[1]), pageOrDecision: Number(match[2]),
      }),
    },
    {
      kind: 'statute_cap',
      regex: /\b([A-Z][A-Za-z0-9&'/-]*(?:\s+[A-Z][A-Za-z0-9&'/-]*)*\s+Act)\s*\((Cap\.?\s*[0-9A-Z]+(?:\s*,\s*\d{4}\s+Rev\s+Ed)?)\)/g,
      map: (match, start) => ({
        kind: 'statute_cap', text: match[0], start, end: start + match[0].length,
        statuteName: match[1], capNumber: match[2].replace(/\s+/g, ' ').trim(),
      }),
    },
  ],
  legalSourceDomains: {
    caseLaw: ['judiciary.gov.sg', 'singaporelawwatch.sg'],
    statutes: ['sso.agc.gov.sg', 'agc.gov.sg'],
  },
  systemPromptAddition: `You are specialized in Singapore law. Use proper Singapore citation formats:
- [YYYY] X SLR(R) XXX, [YYYY] SLR XXX, [YYYY] SGCA XX, [YYYY] SGHC XX
- Statute format: Act Name (Cap. XX, YYYY Rev Ed)`,
  templateIds: ['nda-sg', 'employment-sg', 'mou-sg', 'tenancy-sg', 'board-resolution-sg', 'share-transfer-sg'],
};
