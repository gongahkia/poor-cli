/**
 * Browser-based text analysis utilities
 * No external AI service required
 */

import nlp from 'compromise';

export interface TextStatistics {
  characters: number;
  charactersNoSpaces: number;
  words: number;
  sentences: number;
  paragraphs: number;
  averageWordLength: number;
  averageSentenceLength: number;
  readingTimeMinutes: number;
  speakingTimeMinutes: number;
}

export interface ReadabilityScores {
  fleschReadingEase: number;
  fleschKincaidGrade: number;
  interpretation: string;
}

export interface KeywordResult {
  word: string;
  count: number;
  frequency: number;
}

export interface DocumentStructure {
  hasNumberedSections: boolean;
  hasLetterSections: boolean;
  hasBulletPoints: boolean;
  hasDefinitions: boolean;
  detectedSections: string[];
}

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

function forEachLine(text: string, callback: (line: string) => void): void {
  let start = 0;
  while (start <= text.length) {
    let end = text.indexOf('\n', start);
    if (end === -1) end = text.length;
    callback(text.slice(start, end));
    if (end === text.length) break;
    start = end + 1;
  }
}

/**
 * Calculate basic text statistics
 */
export function getTextStatistics(text: string): TextStatistics {
  const characters = text.length;
  const charactersNoSpaces = text.replace(/\s/g, '').length;
  const words = text.split(/\s+/).filter((w) => w.length > 0).length;
  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 0).length;
  const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim().length > 0).length;

  const averageWordLength = words > 0 ? charactersNoSpaces / words : 0;
  const averageSentenceLength = sentences > 0 ? words / sentences : 0;

  // Average reading speed: 200 words per minute
  const readingTimeMinutes = Math.ceil(words / 200);
  // Average speaking speed: 150 words per minute
  const speakingTimeMinutes = Math.ceil(words / 150);

  return {
    characters,
    charactersNoSpaces,
    words,
    sentences,
    paragraphs,
    averageWordLength: Math.round(averageWordLength * 10) / 10,
    averageSentenceLength: Math.round(averageSentenceLength * 10) / 10,
    readingTimeMinutes,
    speakingTimeMinutes,
  };
}

/**
 * Calculate readability scores
 */
export function getReadabilityScores(text: string): ReadabilityScores {
  const stats = getTextStatistics(text);

  // Count syllables (approximate)
  const syllableCount = countSyllables(text);

  // Flesch Reading Ease: 206.835 - 1.015 * (words/sentences) - 84.6 * (syllables/words)
  const fleschReadingEase = Math.round(
    206.835 -
      1.015 * (stats.words / Math.max(stats.sentences, 1)) -
      84.6 * (syllableCount / Math.max(stats.words, 1))
  );

  // Flesch-Kincaid Grade Level: 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59
  const fleschKincaidGrade =
    Math.round(
      (0.39 * (stats.words / Math.max(stats.sentences, 1)) +
        11.8 * (syllableCount / Math.max(stats.words, 1)) -
        15.59) *
        10
    ) / 10;

  let interpretation: string;
  if (fleschReadingEase >= 90) {
    interpretation = 'Very Easy - 5th grade level';
  } else if (fleschReadingEase >= 80) {
    interpretation = 'Easy - 6th grade level';
  } else if (fleschReadingEase >= 70) {
    interpretation = 'Fairly Easy - 7th grade level';
  } else if (fleschReadingEase >= 60) {
    interpretation = 'Standard - 8th-9th grade level';
  } else if (fleschReadingEase >= 50) {
    interpretation = 'Fairly Difficult - 10th-12th grade level';
  } else if (fleschReadingEase >= 30) {
    interpretation = 'Difficult - College level';
  } else {
    interpretation = 'Very Difficult - Professional/Legal level';
  }

  return {
    fleschReadingEase: Math.max(0, Math.min(100, fleschReadingEase)),
    fleschKincaidGrade: Math.max(0, fleschKincaidGrade),
    interpretation,
  };
}

/**
 * Approximate syllable count
 */
function countSyllables(text: string): number {
  const words = text.toLowerCase().split(/\s+/);
  let count = 0;

  for (const word of words) {
    count += countWordSyllables(word);
  }

  return count;
}

function countWordSyllables(word: string): number {
  word = word.replace(/[^a-z]/g, '');
  if (word.length <= 3) return 1;

  word = word.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, '');
  word = word.replace(/^y/, '');

  const matches = word.match(/[aeiouy]{1,2}/g);
  return matches ? matches.length : 1;
}

/**
 * Extract keywords using frequency analysis
 */
export function extractKeywords(text: string, topN: number = 10): KeywordResult[] {
  // Common stop words to filter out
  const stopWords = new Set([
    'the',
    'a',
    'an',
    'and',
    'or',
    'but',
    'in',
    'on',
    'at',
    'to',
    'for',
    'of',
    'with',
    'by',
    'from',
    'as',
    'is',
    'was',
    'are',
    'were',
    'been',
    'be',
    'have',
    'has',
    'had',
    'do',
    'does',
    'did',
    'will',
    'would',
    'could',
    'should',
    'may',
    'might',
    'must',
    'shall',
    'this',
    'that',
    'these',
    'those',
    'it',
    'its',
    'they',
    'them',
    'their',
    'we',
    'us',
    'our',
    'you',
    'your',
    'he',
    'him',
    'his',
    'she',
    'her',
    'i',
    'me',
    'my',
    'not',
    'no',
    'yes',
    'if',
    'then',
    'else',
    'when',
    'where',
    'which',
    'who',
    'whom',
    'what',
    'how',
    'why',
    'all',
    'each',
    'every',
    'both',
    'few',
    'more',
    'most',
    'other',
    'some',
    'such',
    'only',
    'own',
    'same',
    'so',
    'than',
    'too',
    'very',
    'just',
    'also',
    'now',
    'here',
    'there',
    'any',
    'many',
    'much',
  ]);

  const wordCounts = new Map<string, number>();
  let totalWords = 0;

  for (const chunk of chunkText(text, NLP_CHUNK_SIZE)) {
    const doc = nlp(chunk);
    // Get nouns and noun phrases as they're usually the most meaningful
    const nouns = doc.nouns().out('array') as string[];
    const terms = doc.terms().out('array') as string[];
    const allWords = [...nouns, ...terms];
    totalWords += allWords.length;

    for (const word of allWords) {
      const normalized = word.toLowerCase().trim();
      if (normalized.length > 2 && !stopWords.has(normalized)) {
        wordCounts.set(normalized, (wordCounts.get(normalized) || 0) + 1);
      }
    }
  }

  const sorted = Array.from(wordCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([word, count]) => ({
      word,
      count,
      frequency: totalWords > 0 ? Math.round((count / totalWords) * 10000) / 100 : 0, // percentage
    }));

  return sorted;
}

/**
 * Analyze document structure (useful for legal documents)
 */
export function analyzeDocumentStructure(text: string): DocumentStructure {
  // Check for numbered sections (1., 2., 1.1, etc.)
  const numberedPattern = /^\s*\d+\.(\d+\.?)*\s+/;
  // Check for letter sections (a), (b), (i), (ii), etc.
  const letterPattern = /^\s*\([a-z]\)|\([ivx]+\)/i;
  // Check for bullet points
  const bulletPattern = /^\s*[-•*]\s+/;
  // Check for definitions (common in legal docs)
  const definitionPattern = /"[^"]+"\s+(means|refers to|shall mean)/i;
  const hasDefinitions = definitionPattern.test(text);

  // Detect section headings (ALL CAPS or Title Case followed by content)
  const sectionPattern = /^([A-Z][A-Z\s]+[A-Z]|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$/;
  const detectedSections: string[] = [];
  let hasNumberedSections = false;
  let hasLetterSections = false;
  let hasBulletPoints = false;

  forEachLine(text, (line) => {
    if (!hasNumberedSections && numberedPattern.test(line)) {
      hasNumberedSections = true;
    }
    if (!hasLetterSections && letterPattern.test(line)) {
      hasLetterSections = true;
    }
    if (!hasBulletPoints && bulletPattern.test(line)) {
      hasBulletPoints = true;
    }
    if (detectedSections.length < 20) {
      const trimmed = line.trim();
      if (trimmed.length > 3 && sectionPattern.test(trimmed)) {
        detectedSections.push(trimmed);
      }
    }
  });

  return {
    hasNumberedSections,
    hasLetterSections,
    hasBulletPoints,
    hasDefinitions,
    detectedSections,
  };
}

/**
 * Format text analysis results as markdown
 */
export function formatTextAnalysis(text: string): string {
  const stats = getTextStatistics(text);
  const readability = getReadabilityScores(text);
  const keywords = extractKeywords(text, 10);
  const structure = analyzeDocumentStructure(text);

  let output = '## Document Analysis Results\n\n';

  // Statistics
  output += '### Text Statistics\n';
  output += `| Metric | Value |\n`;
  output += `|--------|-------|\n`;
  output += `| Words | ${stats.words.toLocaleString()} |\n`;
  output += `| Sentences | ${stats.sentences.toLocaleString()} |\n`;
  output += `| Paragraphs | ${stats.paragraphs.toLocaleString()} |\n`;
  output += `| Characters | ${stats.characters.toLocaleString()} |\n`;
  output += `| Avg. Word Length | ${stats.averageWordLength} chars |\n`;
  output += `| Avg. Sentence Length | ${stats.averageSentenceLength} words |\n`;
  output += `| Reading Time | ~${stats.readingTimeMinutes} min |\n`;
  output += `| Speaking Time | ~${stats.speakingTimeMinutes} min |\n\n`;

  // Readability
  output += '### Readability\n';
  output += `- **Flesch Reading Ease:** ${readability.fleschReadingEase}/100\n`;
  output += `- **Flesch-Kincaid Grade:** ${readability.fleschKincaidGrade}\n`;
  output += `- **Interpretation:** ${readability.interpretation}\n\n`;

  // Keywords
  if (keywords.length > 0) {
    output += '### Key Terms\n';
    output += `| Term | Occurrences |\n`;
    output += `|------|-------------|\n`;
    for (const kw of keywords) {
      output += `| ${kw.word} | ${kw.count} |\n`;
    }
    output += '\n';
  }

  // Structure
  output += '### Document Structure\n';
  const structureFeatures = [];
  if (structure.hasNumberedSections) structureFeatures.push('Numbered sections');
  if (structure.hasLetterSections) structureFeatures.push('Letter/Roman sections');
  if (structure.hasBulletPoints) structureFeatures.push('Bullet points');
  if (structure.hasDefinitions) structureFeatures.push('Definitions section');

  if (structureFeatures.length > 0) {
    output += `**Detected features:** ${structureFeatures.join(', ')}\n\n`;
  } else {
    output += 'No structured formatting detected.\n\n';
  }

  if (structure.detectedSections.length > 0) {
    output += '**Section headings found:**\n';
    for (const section of structure.detectedSections.slice(0, 10)) {
      output += `- ${section}\n`;
    }
    output += '\n';
  }

  output += '---\n*Analyzed using local NLP processing (no AI service required)*';

  return output;
}
