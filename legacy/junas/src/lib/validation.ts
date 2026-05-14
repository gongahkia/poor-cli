import { z } from 'zod';

/**
 * Validation schemas for API endpoints using Zod
 */

// Message schema for chat
export const MessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string().min(1, 'Message content cannot be empty').max(50000, 'Message too long'),
});

// Chat endpoint schema
// Chat endpoint schema
export const ChatRequestSchema = z.object({
  messages: z.array(MessageSchema).min(1, 'At least one message is required'),
  provider: z.string().optional(),
  apiKey: z.string().optional(),
  tools: z.array(z.any()).optional(),
  options: z
    .object({
      model: z.string().optional(),
      temperature: z.number().optional(),
      maxTokens: z.number().optional(),
      stream: z.boolean().optional(),
    })
    .optional(),
});

// Tool endpoints common schema
export const TextInputSchema = z.object({
  text: z
    .string()
    .min(1, 'Text is required')
    .max(100000, 'Text exceeds maximum length of 100,000 characters'),
});

// Contract analysis schema
export const AnalyzeRequestSchema = z.object({
  text: z
    .string()
    .min(10, 'Text too short for analysis')
    .max(100000, 'Text exceeds maximum length'),
  type: z.enum(['contract', 'case', 'statute']).optional(),
});

// Summarization schema
export const SummarizeRequestSchema = z.object({
  text: z
    .string()
    .min(10, 'Text too short for summarization')
    .max(100000, 'Text exceeds maximum length'),
  type: z.enum(['contract', 'case', 'statute', 'general']).optional(),
});

// Legal search schema
export const SearchRequestSchema = z.object({
  query: z.string().min(2, 'Search query too short').max(500, 'Search query too long'),
  type: z.enum(['statute', 'case', 'regulation', 'all']).optional(),
  limit: z.number().min(1).max(100).optional(),
});

// NER schema
export const NERRequestSchema = z.object({
  text: z.string().min(1, 'Text is required').max(100000, 'Text exceeds maximum length'),
  entityTypes: z.array(z.enum(['PERSON', 'ORG', 'DATE', 'MONEY', 'LAW', 'GPE'])).optional(),
});

/**
 * Validate data against a schema
 */
export function validateData<T>(
  schema: z.ZodSchema<T>,
  data: unknown
): { success: true; data: T } | { success: false; error: string } {
  try {
    const validData = schema.parse(data);
    return { success: true, data: validData };
  } catch (error: unknown) {
    if (error instanceof z.ZodError) {
      const firstError = error.issues[0];
      return {
        success: false,
        error: firstError?.message || 'Validation failed',
      };
    }
    return { success: false, error: 'Validation failed' };
  }
}
