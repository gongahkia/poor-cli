import { describe, expect, it } from 'vitest';
import {
  extractSingaporeCitations,
  normalizeExtractedCitations,
  validateCitations,
} from '@/lib/citations';

describe('citation extraction and validation', () => {
  it('extracts and validates common Singapore citation formats', () => {
    const text = `
      In [2020] 2 SLR 123 and [2021] SGCA 5, the courts addressed the issue.
      Reference was also made to Evidence Act (Cap. 97, 1997 Rev Ed).
    `;

    const extracted = extractSingaporeCitations(text);
    const normalized = normalizeExtractedCitations(extracted);
    const validated = validateCitations(normalized);

    expect(extracted.length).toBeGreaterThanOrEqual(3);
    expect(validated.some((citation) => citation.normalizedText.includes('SLR'))).toBe(true);
    expect(
      validated.some((citation) => citation.normalizedText.includes('Evidence Act (Cap. 97'))
    ).toBe(true);
    expect(validated.some((citation) => citation.validationStatus === 'valid')).toBe(true);
  });

  it('flags malformed citation-like inputs', () => {
    const text = 'Potential citation: [3020] SGCA ???';
    const validated = validateCitations(
      normalizeExtractedCitations(extractSingaporeCitations(text))
    );

    expect(validated.every((citation) => citation.validationStatus !== 'valid')).toBe(true);
  });
});
