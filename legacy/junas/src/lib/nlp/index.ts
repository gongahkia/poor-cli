/**
 * Local NLP services - no AI required
 */

export {
  extractEntities,
  formatEntityResults,
  type ExtractedEntity,
  type EntityExtractionResult,
} from './entity-extractor';

export {
  getTextStatistics,
  getReadabilityScores,
  extractKeywords,
  analyzeDocumentStructure,
  formatTextAnalysis,
  type TextStatistics,
  type ReadabilityScores,
  type KeywordResult,
  type DocumentStructure,
} from './text-analyzer';
