/// <reference lib="webworker" />

import { extractEntities, formatEntityResults } from './entity-extractor';
import {
  getTextStatistics,
  getReadabilityScores,
  extractKeywords,
  analyzeDocumentStructure,
  formatTextAnalysis,
} from './text-analyzer';

type WorkerTaskCommand = 'extract-entities' | 'analyze-document';

interface WorkerRequest {
  id: string;
  command: WorkerTaskCommand;
  text: string;
}

interface WorkerProgressMessage {
  id: string;
  type: 'progress';
  content: string;
}

interface WorkerResultMessage {
  id: string;
  type: 'result';
  content: string;
}

interface WorkerErrorMessage {
  id: string;
  type: 'error';
  error: string;
}

type WorkerResponse = WorkerProgressMessage | WorkerResultMessage | WorkerErrorMessage;

const workerGlobal = self as unknown as DedicatedWorkerGlobalScope;

function emitProgress(id: string, content: string) {
  const message: WorkerProgressMessage = { id, type: 'progress', content };
  workerGlobal.postMessage(message);
}

function handleExtractEntities(id: string, text: string): string {
  emitProgress(id, '**Entity Extraction**\n\nParsing document...');
  const result = extractEntities(text);
  emitProgress(
    id,
    `**Entity Extraction**\n\nFound ${result.summary.total} entities. Formatting results...`
  );
  return formatEntityResults(result);
}

function handleAnalyzeDocument(id: string, text: string): string {
  emitProgress(id, '**Document Analysis**\n\nComputing text statistics...');
  const stats = getTextStatistics(text);
  emitProgress(
    id,
    `**Document Analysis**\n\nProcessed ${stats.words.toLocaleString()} words. Calculating readability...`
  );
  const readability = getReadabilityScores(text);
  emitProgress(
    id,
    `**Document Analysis**\n\nReadability grade ${readability.fleschKincaidGrade}. Extracting key terms...`
  );
  const keywords = extractKeywords(text, 10);
  emitProgress(
    id,
    `**Document Analysis**\n\nCaptured ${keywords.length} high-signal terms. Mapping structure...`
  );
  const structure = analyzeDocumentStructure(text);
  emitProgress(
    id,
    `**Document Analysis**\n\nDetected ${structure.detectedSections.length} section headings. Finalizing report...`
  );
  return formatTextAnalysis(text);
}

workerGlobal.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const { id, command, text } = event.data;

  try {
    let content = '';
    if (command === 'extract-entities') {
      content = handleExtractEntities(id, text);
    } else if (command === 'analyze-document') {
      content = handleAnalyzeDocument(id, text);
    } else {
      throw new Error(`Unsupported worker command: ${command}`);
    }

    const message: WorkerResultMessage = { id, type: 'result', content };
    workerGlobal.postMessage(message);
  } catch (error) {
    const message: WorkerErrorMessage = {
      id,
      type: 'error',
      error: error instanceof Error ? error.message : String(error),
    };
    workerGlobal.postMessage(message);
  }
};

export {};
