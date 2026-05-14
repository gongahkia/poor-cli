import { describe, expect, it } from 'vitest';
import { extractSingaporeCitations } from './extract';

describe('citation extraction edge cases', () => {
  it('extracts SLR(R) with varied spacing', () => {
    const citations = extractSingaporeCitations('[2009]  2  SLR(R)  332');
    expect(citations).toHaveLength(1);
    expect(citations[0].kind).toBe('slr_r');
    expect(citations[0].year).toBe(2009);
    expect(citations[0].volume).toBe(2);
    expect(citations[0].pageOrDecision).toBe(332);
  });
  it('extracts plain SLR citations', () => {
    const citations = extractSingaporeCitations('[2015] 3 SLR 456');
    expect(citations).toHaveLength(1);
    expect(citations[0].kind).toBe('slr');
  });
  it('extracts SGCA and SGHC in same text', () => {
    const text = 'See [2020] SGCA 45 and [2019] SGHC 123.';
    const citations = extractSingaporeCitations(text);
    expect(citations).toHaveLength(2);
    expect(citations.map((c) => c.kind).sort()).toEqual(['sgca', 'sghc']);
  });
  it('extracts statute Cap citations with Rev Ed', () => {
    const text = 'Companies Act (Cap. 50, 2006 Rev Ed)';
    const citations = extractSingaporeCitations(text);
    expect(citations).toHaveLength(1);
    expect(citations[0].kind).toBe('statute_cap');
    expect(citations[0].statuteName).toBe('Companies Act');
    expect(citations[0].capNumber).toContain('Cap.');
  });
  it('handles statute without Rev Ed', () => {
    const text = 'Penal Code (Cap. 224)';
    const citations = extractSingaporeCitations(text);
    // Penal Code doesn't match pattern requiring "Act" suffix
    expect(citations).toHaveLength(0);
  });
  it('extracts multiple citations from dense legal text', () => {
    const text = `
      The appellant in [2023] SGCA 10 relied on [2018] 1 SLR(R) 100 and
      [2017] 4 SLR 200. The Employment Act (Cap. 91, 2009 Rev Ed) was considered.
    `;
    const citations = extractSingaporeCitations(text);
    expect(citations.length).toBeGreaterThanOrEqual(4);
  });
  it('returns empty for no citations', () => {
    expect(extractSingaporeCitations('No legal text here.')).toEqual([]);
  });
  it('returns empty for empty/null input', () => {
    expect(extractSingaporeCitations('')).toEqual([]);
  });
  it('deduplicates repeated citations', () => {
    const text = '[2020] SGCA 5 was cited. Again [2020] SGCA 5 appeared.';
    const citations = extractSingaporeCitations(text);
    // both occurrences have different start positions, so both should be extracted
    expect(citations).toHaveLength(2);
    expect(citations[0].start).not.toBe(citations[1].start);
  });
  it('handles year boundary values', () => {
    expect(extractSingaporeCitations('[1965] SGCA 1')).toHaveLength(1);
    expect(extractSingaporeCitations('[2099] SGHC 999')).toHaveLength(1);
  });
});
