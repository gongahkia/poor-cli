import { useEffect, useState } from 'react';
import { estimateTokens, estimateCost } from '@/lib/ai/token-utils';

interface TokenCounterProps {
  content: string;
  isStreaming?: boolean;
  provider?: string;
  model?: string;
  responseTime?: number; // in milliseconds
}

// Format time in seconds
function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function TokenCounter({ content, isStreaming, provider = 'gemini', model = 'gemini-2.0-flash-exp', responseTime }: TokenCounterProps) {
  const [tokens, setTokens] = useState(0);
  const [cost, setCost] = useState(0);

  useEffect(() => {
    const estimatedTokens = estimateTokens(content);
    setTokens(estimatedTokens);
    setCost(estimateCost(estimatedTokens, provider, model, 'input')); // Input cost for user typing
  }, [content, provider, model]);

  if (!content) return null;

  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <div className="flex items-center gap-1.5">
        <span className="font-mono">{tokens.toLocaleString()}</span>
        <span>tokens</span>
        {isStreaming && (
          <span className="animate-pulse">...</span>
        )}
      </div>
      {responseTime && (
        <div className="flex items-center gap-1.5">
          <span className="opacity-60">·</span>
          <span className="font-mono">{formatTime(responseTime)}</span>
        </div>
      )}
      {cost > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="opacity-60">·</span>
          <span className="font-mono">${cost.toFixed(4)}</span>
          <span>est.</span>
        </div>
      )}
    </div>
  );
}
