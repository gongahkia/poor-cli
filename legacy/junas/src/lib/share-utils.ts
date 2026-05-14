import LZString from 'lz-string';
import { Message } from '@/types/chat';

export interface SharedData {
  messages: Message[];
  nodeMap?: Record<string, Message>;
  currentLeafId?: string;
  version?: number;
}

/**
 * Compresses the chat data into a URL-safe string.
 */
export function compressChat(data: Message[] | SharedData): string {
  try {
    const json = JSON.stringify(data);
    return LZString.compressToEncodedURIComponent(json);
  } catch (error) {
    console.error('Failed to compress chat:', error);
    return '';
  }
}

/**
 * Decompresses a URL-safe string back into chat data.
 */
export function decompressChat(compressed: string): SharedData | null {
  try {
    const json = LZString.decompressFromEncodedURIComponent(compressed);
    if (!json) return null;
    
    const data = JSON.parse(json);
    
    // Backward compatibility: if array, it's just messages
    if (Array.isArray(data)) {
      return { messages: data };
    }
    
    return data as SharedData;
  } catch (error) {
    console.error('Failed to decompress chat:', error);
    return null;
  }
}
