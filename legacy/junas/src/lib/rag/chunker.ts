export interface TextChunk {
  id: string;
  text: string;
  index: number;
}

const DEFAULT_CHUNK_SIZE = 512; // characters
const DEFAULT_OVERLAP = 64;

export function chunkText(
  text: string,
  chunkSize = DEFAULT_CHUNK_SIZE,
  overlap = DEFAULT_OVERLAP,
  prefix = 'chunk',
): TextChunk[] {
  const chunks: TextChunk[] = [];
  let offset = 0;
  let index = 0;
  while (offset < text.length) {
    const end = Math.min(offset + chunkSize, text.length);
    let slice = text.slice(offset, end);
    // try to break at sentence boundary
    if (end < text.length) {
      const lastPeriod = slice.lastIndexOf('. ');
      const lastNewline = slice.lastIndexOf('\n');
      const breakAt = Math.max(lastPeriod, lastNewline);
      if (breakAt > chunkSize * 0.3) {
        slice = slice.slice(0, breakAt + 1);
      }
    }
    chunks.push({ id: `${prefix}_${index}`, text: slice.trim(), index });
    offset += slice.length - overlap;
    if (offset <= chunks[chunks.length - 1]?.text.length && offset > 0) {
      offset = end; // prevent infinite loop on tiny text
    }
    index++;
  }
  return chunks.filter((c) => c.text.length > 0);
}
