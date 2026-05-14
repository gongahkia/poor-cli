import Fuse from 'fuse.js'
import { Message } from '@/types/chat'

export interface SearchResult {
  message: Message
  score: number
  matchedText: string
}

/**
 * Search through conversation messages using fuzzy search
 * @param query - Search query string
 * @param messages - Array of messages to search through
 * @param options - Search configuration options
 * @returns Array of search results with relevance scores
 */
export function searchMessages(
  query: string,
  messages: Message[],
  options?: {
    threshold?: number // 0.0 = perfect match, 1.0 = match anything
    limit?: number // Maximum number of results
  }
): SearchResult[] {
  if (!query.trim()) {
    return []
  }

  const fuse = new Fuse(messages, {
    keys: ['content'], // Search in message content
    threshold: options?.threshold || 0.4, // Fuzzy matching threshold
    includeScore: true,
    minMatchCharLength: 2,
    ignoreLocation: true, // Search anywhere in the string
  })

  const results = fuse.search(query, {
    limit: options?.limit || 50,
  })

  return results.map((result) => ({
    message: result.item,
    score: result.score || 0,
    matchedText: extractMatchedText(result.item.content, query),
  }))
}

/**
 * Extract a snippet of text around the matched query
 * @param content - Full message content
 * @param query - Search query
 * @returns Snippet with the matched text highlighted
 */
function extractMatchedText(content: string, query: string): string {
  const lowerContent = content.toLowerCase()
  const lowerQuery = query.toLowerCase()
  const index = lowerContent.indexOf(lowerQuery)

  if (index === -1) {
    // If exact match not found, return first 150 chars
    return content.slice(0, 150) + (content.length > 150 ? '...' : '')
  }

  // Extract context around the match
  const contextLength = 75
  const start = Math.max(0, index - contextLength)
  const end = Math.min(content.length, index + query.length + contextLength)

  let snippet = content.slice(start, end)

  if (start > 0) snippet = '...' + snippet
  if (end < content.length) snippet = snippet + '...'

  return snippet
}

/**
 * Search through multiple conversations
 * @param query - Search query string
 * @param conversations - Array of conversation arrays
 * @returns Grouped search results by conversation
 */
export function searchConversations(
  query: string,
  conversations: Message[][]
): { conversationIndex: number; results: SearchResult[] }[] {
  if (!query.trim()) {
    return []
  }

  return conversations
    .map((messages, index) => ({
      conversationIndex: index,
      results: searchMessages(query, messages),
    }))
    .filter((item) => item.results.length > 0)
}

/**
 * Search through multiple conversations objects
 * @param query - Search query string
 * @param conversations - Array of Conversation objects
 * @returns Grouped search results by conversation
 */
export function searchGlobalConversations(
  query: string,
  conversations: { id: string; title: string; messages: Message[] }[]
): { conversationId: string; title: string; results: SearchResult[] }[] {
  if (!query.trim()) {
    return []
  }

  return conversations
    .map((conv) => ({
      conversationId: conv.id,
      title: conv.title,
      results: searchMessages(query, conv.messages),
    }))
    .filter((item) => item.results.length > 0)
}

/**
 * Highlight search query in text
 * @param text - Text to highlight
 * @param query - Query to highlight
 * @returns Text with query wrapped in <mark> tags
 */
export function highlightQuery(text: string, query: string): string {
  if (!query.trim()) return text

  const regex = new RegExp(`(${escapeRegExp(query)})`, 'gi')
  return text.replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-800">$1</mark>')
}

/**
 * Escape special regex characters
 */
function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
