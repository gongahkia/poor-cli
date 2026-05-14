import { useEffect, useRef, memo, useState, lazy, Suspense, useMemo } from 'react';
import { Message } from '@/types/chat';
import { FileText, ChevronLeft, ChevronRight, Edit2 } from 'lucide-react';
import { StorageManager } from '@/lib/storage';
import { getBranchSiblings } from '@/lib/chat-tree';
import {
  extractSingaporeCitations,
  normalizeExtractedCitations,
  validateCitations,
} from '@/lib/citations';
import { parseRiskFromAIResponse, type RiskAssessment } from '@/lib/risk/risk-parser';
import { RiskMatrix } from './RiskMatrix';

const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));

interface MessageListProps {
  messages: Message[];
  nodeMap?: Record<string, Message>;
  isLoading: boolean;
  onCopyMessage: (content: string) => void;
  onRegenerateMessage: (messageId: string) => void;
  onEditMessage?: (messageId: string, newContent: string) => void;
  onBranchSwitch?: (messageId: string, direction: 'prev' | 'next') => void;
  scrollToMessageId?: string;
}

interface MessageItemProps {
  message: Message;
  nodeMap?: Record<string, Message>;
  onCopyMessage: (content: string) => void;
  onRegenerateMessage: (messageId: string) => void;
  onEditMessage?: (messageId: string, newContent: string) => void;
  onBranchSwitch?: (messageId: string, direction: 'prev' | 'next') => void;
}

// Memoized message item component to prevent unnecessary re-renders
const MessageItemComponent = ({
  message,
  nodeMap,
  onCopyMessage,
  onRegenerateMessage,
  onEditMessage,
  onBranchSwitch,
}: MessageItemProps) => {
  const userName = StorageManager.getSettings().userName || 'User';
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);

  // Branching logic
  const siblings = nodeMap ? getBranchSiblings(nodeMap, message.id) : [message.id];
  const currentSiblingIndex = siblings.indexOf(message.id);
  const totalSiblings = siblings.length;

  const handleSaveEdit = () => {
    if (editContent.trim() !== message.content) {
      onEditMessage?.(message.id, editContent);
    }
    setIsEditing(false);
  };

  const citationWarnings = useMemo(() => {
    if (message.role !== 'assistant') return [];
    const extracted = extractSingaporeCitations(message.content);
    if (extracted.length === 0) return [];
    const normalized = normalizeExtractedCitations(extracted);
    return validateCitations(normalized).filter(
      (citation) => citation.validationStatus !== 'valid'
    );
  }, [message.role, message.content]);

  const riskAssessment = useMemo((): RiskAssessment | null => {
    if (message.role !== 'assistant') return null;
    const content = message.content.toLowerCase();
    const hasRiskKeywords = content.includes('risk assessment') ||
      content.includes('risk rating') ||
      (content.includes('high') && content.includes('medium') && content.includes('low') &&
        (content.includes('contract') || content.includes('compliance') || content.includes('due diligence')));
    if (!hasRiskKeywords) return null;
    const parsed = parseRiskFromAIResponse(message.content);
    return parsed.flags.length > 0 ? parsed : null;
  }, [message.role, message.content]);

  return (
    <div
      className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in-up group`}
    >
      <div
        className={`flex w-full md:max-w-[80%] ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'} items-start gap-3`}
      >
        <div
          className={`flex-1 border ${
            message.role === 'user'
              ? 'bg-primary/5 border-primary/30'
              : 'bg-muted/20 border-muted-foreground/30'
          } font-mono relative`}
        >
          <div className="space-y-3 px-4 py-3">
            {/* Branch Navigation */}
            {totalSiblings > 1 && (
              <div
                className={`absolute -top-3 ${message.role === 'user' ? 'right-2' : 'left-2'} flex items-center gap-1 bg-background border rounded-full px-1.5 py-0.5 text-[10px] text-muted-foreground shadow-sm`}
              >
                <button
                  onClick={() => onBranchSwitch?.(message.id, 'prev')}
                  disabled={currentSiblingIndex === 0}
                  className="hover:text-foreground disabled:opacity-30"
                >
                  <ChevronLeft className="h-3 w-3" />
                </button>
                <span className="font-mono">
                  {currentSiblingIndex + 1}/{totalSiblings}
                </span>
                <button
                  onClick={() => onBranchSwitch?.(message.id, 'next')}
                  disabled={currentSiblingIndex === totalSiblings - 1}
                  className="hover:text-foreground disabled:opacity-30"
                >
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            )}

            {/* Attachments */}
            {message.attachments && message.attachments.length > 0 && (
              <div className="space-y-2">
                {message.attachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-background/60 text-sm text-foreground border-none"
                  >
                    <FileText className="w-4 h-4" />
                    <span className="truncate max-w-[320px]" title={attachment.name}>
                      {attachment.name}
                    </span>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                      {Math.round(attachment.size / 1024)}KB
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Message content */}
            <div className={`prose prose-sm md:prose-base max-w-none leading-relaxed relative`}>
              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full min-h-[100px] p-2 text-sm bg-background border rounded-md focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setIsEditing(false)}
                      className="text-xs px-2 py-1 bg-muted hover:bg-muted/80 rounded"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveEdit}
                      className="text-xs px-2 py-1 bg-primary text-primary-foreground hover:bg-primary/90 rounded"
                    >
                      Save & Switch Branch
                    </button>
                  </div>
                </div>
              ) : message.role === 'assistant' ? (
                <Suspense fallback={<div className="h-4 w-full animate-pulse bg-muted rounded" />}>
                  <MarkdownRenderer content={message.content} />
                </Suspense>
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}
            </div>

            {/* Risk Matrix */}
            {riskAssessment && <RiskMatrix assessment={riskAssessment} />}

            {/* Citations */}
            {message.citations && message.citations.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-semibold text-muted-foreground">Sources:</div>
                {message.citations.map((citation) => (
                  <a
                    key={citation.id}
                    href={citation.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-xs text-primary hover:underline"
                  >
                    {citation.title}
                  </a>
                ))}
              </div>
            )}

            {citationWarnings.length > 0 && (
              <div className="space-y-1 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5">
                <div className="text-xs font-semibold text-amber-700">Citation warnings:</div>
                {citationWarnings.map((citation) => {
                  const issueText = citation.validationIssues
                    .map((issue) => issue.message)
                    .join(' ');
                  const title =
                    citation.validationStatus === 'malformed'
                      ? `[Malformed] ${citation.normalizedText}`
                      : `[Incomplete] ${citation.normalizedText}`;

                  return (
                    <div
                      key={`${citation.kind}-${citation.start}-${citation.end}`}
                      className="text-xs"
                    >
                      <span className="font-medium">{title}</span>
                      {issueText ? (
                        <span className="text-muted-foreground"> {issueText}</span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Message actions */}
            {!isEditing && (
              <div className="flex items-center gap-1 pt-2 -mx-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onCopyMessage(message.content);
                  }}
                  className="text-xs px-2 py-1 text-muted-foreground/60 hover:text-foreground hover:bg-muted/30 transition-colors font-mono"
                  title="Copy message"
                >
                  [ Copy ]
                </button>
                {message.role === 'assistant' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onRegenerateMessage(message.id);
                    }}
                    className="text-xs px-2 py-1 text-muted-foreground/60 hover:text-foreground hover:bg-muted/30 transition-colors font-mono"
                    title="Regenerate response (new branch)"
                  >
                    [ Regenerate ]
                  </button>
                )}
                {message.role === 'user' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsEditing(true);
                    }}
                    className="text-xs px-2 py-1 text-muted-foreground/60 hover:text-foreground hover:bg-muted/30 transition-colors font-mono flex items-center gap-1"
                    title="Edit message (new branch)"
                  >
                    <Edit2 className="h-3 w-3" /> [ Edit ]
                  </button>
                )}
              </div>
            )}

            {/* Sender label */}
            <div
              className={`pt-2 text-[11px] font-medium text-muted-foreground/70 border-t border-muted-foreground/20 mt-3 flex flex-wrap gap-2 items-center ${
                message.role === 'user' ? 'justify-end' : 'justify-between'
              }`}
            >
              <span>{message.role === 'assistant' ? '> Junas' : `> ${userName}`}</span>

              {(message.tokenCount || message.cost || message.responseTime) && (
                <span className="flex items-center gap-2 opacity-60 font-mono text-[10px]">
                  {message.tokenCount && <span>{message.tokenCount.toLocaleString()} tks</span>}
                  {message.cost !== undefined && message.cost > 0 && (
                    <span>${message.cost.toFixed(5)}</span>
                  )}
                  {message.responseTime && <span>{(message.responseTime / 1000).toFixed(1)}s</span>}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Custom comparison to prevent re-renders unless content actually changes
const arePropsEqual = (prevProps: MessageItemProps, nextProps: MessageItemProps) => {
  return (
    prevProps.message.id === nextProps.message.id &&
    prevProps.message.content === nextProps.message.content &&
    prevProps.message.responseTime === nextProps.message.responseTime &&
    prevProps.nodeMap === nextProps.nodeMap // Need to re-render if tree changes
  );
};

const MessageItem = memo(MessageItemComponent, arePropsEqual);
MessageItem.displayName = 'MessageItem';

import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';

export const MessageList = memo(function MessageList({
  messages,
  nodeMap,
  isLoading,
  onCopyMessage,
  onRegenerateMessage,
  onEditMessage,
  onBranchSwitch,
  scrollToMessageId,
}: MessageListProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Scroll to specific message when scrollToMessageId changes
  useEffect(() => {
    if (scrollToMessageId) {
      const index = messages.findIndex((m) => m.id === scrollToMessageId);
      if (index !== -1 && virtuosoRef.current) {
        virtuosoRef.current.scrollToIndex({ index, align: 'center', behavior: 'smooth' });
      }
    }
  }, [scrollToMessageId, messages]);

  if (messages.length === 0) {
    return null;
  }

  return (
    <div ref={containerRef} className="flex-1 h-full w-full max-w-5xl mx-auto px-3 md:px-8">
      <Virtuoso
        ref={virtuosoRef}
        data={messages}
        followOutput={'smooth'}
        initialTopMostItemIndex={messages.length - 1}
        itemContent={(index, message) => (
          <div className="py-4 md:py-6">
            {message.role === 'system' && message.content === 'loading' ? (
              <div className="flex justify-center py-4">
                <div className="text-sm text-muted-foreground/60 animate-pulse">
                  Summarising your past conversation...
                </div>
              </div>
            ) : (
              <MessageItem
                message={message}
                nodeMap={nodeMap}
                onCopyMessage={onCopyMessage}
                onRegenerateMessage={onRegenerateMessage}
                onEditMessage={onEditMessage}
                onBranchSwitch={onBranchSwitch}
              />
            )}
            {/* Adding the "thinking" indicator at the bottom if this is the last message and it's from user? No, logic was separate div. */}
          </div>
        )}
        components={{
          Footer: () => <div className="pb-4">{/* Spacer at bottom */}</div>,
        }}
        className="no-scrollbar"
      />
    </div>
  );
});
