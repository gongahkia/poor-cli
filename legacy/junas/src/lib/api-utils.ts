/**
 * Shared utility functions for API route handlers
 */

/**
 * Calculate overall risk level based on risk flags
 */
export function calculateRiskLevel(riskFlags: any[]): string {
  if (!Array.isArray(riskFlags)) return 'none';

  const highRiskCount = riskFlags.filter(flag => flag.severity === 'high').length;
  const mediumRiskCount = riskFlags.filter(flag => flag.severity === 'medium').length;

  if (highRiskCount > 0) return 'high';
  if (mediumRiskCount > 2) return 'medium';
  if (riskFlags.length > 0) return 'low';
  return 'none';
}

/**
 * Validate text input for tool endpoints
 */
export function validateTextInput(text: any, maxLength: number = 100000): { valid: boolean; error?: string } {
  if (!text || typeof text !== 'string') {
    return { valid: false, error: 'Text is required and must be a string' };
  }

  if (text.trim().length === 0) {
    return { valid: false, error: 'Text cannot be empty' };
  }

  if (text.length > maxLength) {
    return { valid: false, error: `Text too long. Maximum length is ${maxLength.toLocaleString()} characters.` };
  }

  return { valid: true };
}

/**
 * Calculate reading time in minutes (assuming 200 WPM)
 */
export function calculateReadingTime(text: string, wordsPerMinute: number = 200): number {
  const wordCount = text.split(/\s+/).length;
  return Math.ceil(wordCount / wordsPerMinute);
}

/**
 * Count words in text
 */
export function countWords(text: string): number {
  return text.split(/\s+/).filter(word => word.length > 0).length;
}

/**
 * Format API error response with consistent structure
 */
export function formatErrorResponse(error: any, context: string): { error: string; code?: string; success: boolean } {
  console.error(`API error in ${context}:`, error);

  // Check for specific error types
  if (error.message?.includes('timeout')) {
    return {
      error: 'Request timed out. Please try again.',
      code: 'TIMEOUT',
      success: false,
    };
  }

  if (error.message?.includes('network')) {
    return {
      error: 'Network error. Please check your connection.',
      code: 'NETWORK_ERROR',
      success: false,
    };
  }

  // Default error response
  return {
    error: error.message || `${context} failed`,
    code: error.code || 'UNKNOWN_ERROR',
    success: false,
  };
}
