import type { NormalizedCitation } from './normalize';

export type CitationValidationStatus = 'valid' | 'incomplete' | 'malformed';

export interface CitationValidationIssue {
  code: string;
  message: string;
  severity: 'incomplete' | 'malformed';
}

export interface ValidatedCitation extends NormalizedCitation {
  validationStatus: CitationValidationStatus;
  validationIssues: CitationValidationIssue[];
  isValid: boolean;
}

const MIN_REASONABLE_YEAR = 1800;

function isReasonableYear(year: number): boolean {
  return year >= MIN_REASONABLE_YEAR && year <= new Date().getFullYear() + 1;
}

export function validateCitation(citation: NormalizedCitation): ValidatedCitation {
  const issues: CitationValidationIssue[] = [];

  switch (citation.kind) {
    case 'slr_r':
      if (!citation.year || !citation.volume || !citation.pageOrDecision) {
        issues.push({
          code: 'SLR_R_MISSING_FIELDS',
          message: 'SLR(R) citation is missing year, volume, or page number.',
          severity: 'incomplete',
        });
      }
      if (citation.year && !isReasonableYear(citation.year)) {
        issues.push({
          code: 'YEAR_OUT_OF_RANGE',
          message: 'Citation year is outside the expected legal reporting range.',
          severity: 'malformed',
        });
      }
      if (!/^\[\d{4}\]\s+\d+\s+SLR\(R\)\s+\d+$/.test(citation.normalizedText)) {
        issues.push({
          code: 'SLR_R_FORMAT_INVALID',
          message: 'SLR(R) citation format is malformed.',
          severity: 'malformed',
        });
      }
      break;

    case 'slr':
      if (!citation.year || !citation.volume || !citation.pageOrDecision) {
        issues.push({
          code: 'SLR_MISSING_FIELDS',
          message: 'SLR citation is missing year, volume, or page number.',
          severity: 'incomplete',
        });
      }
      if (citation.year && !isReasonableYear(citation.year)) {
        issues.push({
          code: 'YEAR_OUT_OF_RANGE',
          message: 'Citation year is outside the expected legal reporting range.',
          severity: 'malformed',
        });
      }
      if (!/^\[\d{4}\]\s+\d+\s+SLR\s+\d+$/.test(citation.normalizedText)) {
        issues.push({
          code: 'SLR_FORMAT_INVALID',
          message: 'SLR citation format is malformed.',
          severity: 'malformed',
        });
      }
      break;

    case 'sgca':
      if (!citation.year || !citation.pageOrDecision) {
        issues.push({
          code: 'SGCA_MISSING_FIELDS',
          message: 'SGCA citation is missing year or decision number.',
          severity: 'incomplete',
        });
      }
      if (citation.year && !isReasonableYear(citation.year)) {
        issues.push({
          code: 'YEAR_OUT_OF_RANGE',
          message: 'Citation year is outside the expected legal reporting range.',
          severity: 'malformed',
        });
      }
      if (!/^\[\d{4}\]\s+SGCA\s+\d+$/.test(citation.normalizedText)) {
        issues.push({
          code: 'SGCA_FORMAT_INVALID',
          message: 'SGCA citation format is malformed.',
          severity: 'malformed',
        });
      }
      break;

    case 'sghc':
      if (!citation.year || !citation.pageOrDecision) {
        issues.push({
          code: 'SGHC_MISSING_FIELDS',
          message: 'SGHC citation is missing year or decision number.',
          severity: 'incomplete',
        });
      }
      if (citation.year && !isReasonableYear(citation.year)) {
        issues.push({
          code: 'YEAR_OUT_OF_RANGE',
          message: 'Citation year is outside the expected legal reporting range.',
          severity: 'malformed',
        });
      }
      if (!/^\[\d{4}\]\s+SGHC\s+\d+$/.test(citation.normalizedText)) {
        issues.push({
          code: 'SGHC_FORMAT_INVALID',
          message: 'SGHC citation format is malformed.',
          severity: 'malformed',
        });
      }
      break;

    case 'statute_cap':
      if (!citation.statuteName || !citation.capNumber) {
        issues.push({
          code: 'STATUTE_MISSING_FIELDS',
          message: 'Statute citation is missing statute name or cap number.',
          severity: 'incomplete',
        });
      }
      if (!/^.+\s+\(Cap\.\s+[0-9A-Z]+(?:,\s*\d{4}\s+Rev Ed)?\)$/.test(citation.normalizedText)) {
        issues.push({
          code: 'STATUTE_CAP_FORMAT_INVALID',
          message: 'Statute cap citation format is malformed.',
          severity: 'malformed',
        });
      }
      break;

    default:
      issues.push({
        code: 'UNKNOWN_CITATION_KIND',
        message: 'Citation kind is unknown and cannot be validated.',
        severity: 'malformed',
      });
  }

  const validationStatus: CitationValidationStatus = issues.some(
    (issue) => issue.severity === 'malformed'
  )
    ? 'malformed'
    : issues.length > 0
      ? 'incomplete'
      : 'valid';

  return {
    ...citation,
    validationStatus,
    validationIssues: issues,
    isValid: validationStatus === 'valid',
  };
}

export function validateCitations(citations: NormalizedCitation[]): ValidatedCitation[] {
  return citations.map((citation) => validateCitation(citation));
}
