/**
 * Browser-based Named Entity Recognition using compromise.js
 * No external AI service required
 */

import nlp from 'compromise';
import dates from 'compromise-dates';

// Extend compromise with dates plugin
nlp.plugin(dates);

export interface ExtractedEntity {
  text: string;
  type:
    | 'person'
    | 'organization'
    | 'place'
    | 'date'
    | 'money'
    | 'legal_citation'
    | 'email'
    | 'phone'
    | 'url';
  start?: number;
  end?: number;
}

export interface EntityExtractionResult {
  entities: ExtractedEntity[];
  summary: {
    persons: number;
    organizations: number;
    places: number;
    dates: number;
    money: number;
    legalCitations: number;
    emails: number;
    phones: number;
    urls: number;
    total: number;
  };
}

// Singapore legal citation patterns
const LEGAL_CITATION_PATTERNS = [
  // [YYYY] X SLR(R) XXX - Singapore Law Reports (Reissue)
  /\[\d{4}\]\s+\d*\s*SLR\(R\)\s+\d+/gi,
  // [YYYY] SLR XXX - Singapore Law Reports
  /\[\d{4}\]\s+\d*\s*SLR\s+\d+/gi,
  // [YYYY] SGCA XX - Singapore Court of Appeal
  /\[\d{4}\]\s+SGCA\s+\d+/gi,
  // [YYYY] SGHC XX - Singapore High Court
  /\[\d{4}\]\s+SGHC\s+\d+/gi,
  // [YYYY] SGDC XX - Singapore District Court
  /\[\d{4}\]\s+SGDC\s+\d+/gi,
  // [YYYY] SGMC XX - Singapore Magistrate's Court
  /\[\d{4}\]\s+SGMC\s+\d+/gi,
  // Cap XX - Singapore Statutes
  /Cap\.?\s+\d+[A-Z]?/gi,
];

const EMAIL_PATTERN = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
const PHONE_PATTERN = /(?:\+65\s?)?[689]\d{3}\s?\d{4}/g;
const URL_PATTERN = /https?:\/\/[^\s]+/g;
const NLP_CHUNK_SIZE = 12_000;

function chunkText(text: string, chunkSize: number): string[] {
  if (text.length <= chunkSize) return [text];

  const chunks: string[] = [];
  let start = 0;

  while (start < text.length) {
    let end = Math.min(start + chunkSize, text.length);
    if (end < text.length) {
      const newlineBreak = text.lastIndexOf('\n', end);
      const sentenceBreak = text.lastIndexOf('. ', end);
      const bestBreak = Math.max(newlineBreak, sentenceBreak);
      if (bestBreak > start + chunkSize * 0.5) {
        end = bestBreak + 1;
      }
    }
    chunks.push(text.slice(start, end));
    start = end;
  }

  return chunks;
}

function extractRegexMatches(chunk: string, pattern: RegExp): string[] {
  const matches: string[] = [];
  pattern.lastIndex = 0;
  let match = pattern.exec(chunk);
  while (match) {
    matches.push(match[0]);
    match = pattern.exec(chunk);
  }
  pattern.lastIndex = 0;
  return matches;
}

/**
 * Extract entities from text using browser-based NLP
 */
export function extractEntities(text: string): EntityExtractionResult {
  const entities: ExtractedEntity[] = [];
  const chunks = chunkText(text, NLP_CHUNK_SIZE);

  for (const chunk of chunks) {
    const doc = nlp(chunk) as any;

    // Extract people
    doc.people().forEach((match: any) => {
      entities.push({
        text: match.text(),
        type: 'person',
      });
    });

    // Extract organizations
    doc.organizations().forEach((match: any) => {
      entities.push({
        text: match.text(),
        type: 'organization',
      });
    });

    // Extract places
    doc.places().forEach((match: any) => {
      entities.push({
        text: match.text(),
        type: 'place',
      });
    });

    // Extract dates
    doc.dates().forEach((match: any) => {
      entities.push({
        text: match.text(),
        type: 'date',
      });
    });

    // Extract money
    doc.money().forEach((match: any) => {
      entities.push({
        text: match.text(),
        type: 'money',
      });
    });

    // Extract legal citations using regex patterns
    for (const pattern of LEGAL_CITATION_PATTERNS) {
      for (const match of extractRegexMatches(chunk, pattern)) {
        entities.push({
          text: match,
          type: 'legal_citation',
        });
      }
    }

    // Extract emails
    for (const email of extractRegexMatches(chunk, EMAIL_PATTERN)) {
      entities.push({
        text: email,
        type: 'email',
      });
    }

    // Extract phone numbers (Singapore format)
    for (const phone of extractRegexMatches(chunk, PHONE_PATTERN)) {
      entities.push({
        text: phone,
        type: 'phone',
      });
    }

    // Extract URLs
    for (const url of extractRegexMatches(chunk, URL_PATTERN)) {
      entities.push({
        text: url,
        type: 'url',
      });
    }
  }

  // Deduplicate entities
  const uniqueEntities = entities.filter(
    (entity, index, self) =>
      index === self.findIndex((e) => e.text === entity.text && e.type === entity.type)
  );

  // Calculate summary
  const summary = {
    persons: uniqueEntities.filter((e) => e.type === 'person').length,
    organizations: uniqueEntities.filter((e) => e.type === 'organization').length,
    places: uniqueEntities.filter((e) => e.type === 'place').length,
    dates: uniqueEntities.filter((e) => e.type === 'date').length,
    money: uniqueEntities.filter((e) => e.type === 'money').length,
    legalCitations: uniqueEntities.filter((e) => e.type === 'legal_citation').length,
    emails: uniqueEntities.filter((e) => e.type === 'email').length,
    phones: uniqueEntities.filter((e) => e.type === 'phone').length,
    urls: uniqueEntities.filter((e) => e.type === 'url').length,
    total: uniqueEntities.length,
  };

  return {
    entities: uniqueEntities,
    summary,
  };
}

/**
 * Format extraction results as markdown for display
 */
export function formatEntityResults(result: EntityExtractionResult): string {
  const { entities, summary } = result;

  if (summary.total === 0) {
    return 'No entities found in the provided text.';
  }

  let output = '## Entity Extraction Results\n\n';
  output += `**Total entities found: ${summary.total}**\n\n`;

  const sections: { type: ExtractedEntity['type']; label: string; count: number }[] = [
    { type: 'person', label: 'People', count: summary.persons },
    { type: 'organization', label: 'Organizations', count: summary.organizations },
    { type: 'place', label: 'Places', count: summary.places },
    { type: 'date', label: 'Dates', count: summary.dates },
    { type: 'money', label: 'Monetary Values', count: summary.money },
    { type: 'legal_citation', label: 'Legal Citations', count: summary.legalCitations },
    { type: 'email', label: 'Email Addresses', count: summary.emails },
    { type: 'phone', label: 'Phone Numbers', count: summary.phones },
    { type: 'url', label: 'URLs', count: summary.urls },
  ];

  for (const section of sections) {
    if (section.count > 0) {
      output += `### ${section.label} (${section.count})\n`;
      const sectionEntities = entities.filter((e) => e.type === section.type);
      for (const entity of sectionEntities) {
        output += `- ${entity.text}\n`;
      }
      output += '\n';
    }
  }

  output += '---\n*Extracted using local NLP processing (no AI service required)*';

  return output;
}
