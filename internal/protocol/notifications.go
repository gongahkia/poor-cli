package protocol

import "encoding/json"

type StreamChunk struct {
	RequestID          string `json:"requestId"`
	Chunk              string `json:"chunk"`
	Done               bool   `json:"done"`
	Reason             string `json:"reason,omitempty"`
	AuthorConnectionID string `json:"authorConnectionId,omitempty"`
	AuthorDisplayName  string `json:"authorDisplayName,omitempty"`
	AuthorRole         string `json:"authorRole,omitempty"`
}

type ThinkingChunk struct {
	RequestID          string `json:"requestId"`
	Chunk              string `json:"chunk"`
	AuthorConnectionID string `json:"authorConnectionId,omitempty"`
	AuthorDisplayName  string `json:"authorDisplayName,omitempty"`
	AuthorRole         string `json:"authorRole,omitempty"`
}

type ToolEvent struct {
	RequestID          string          `json:"requestId"`
	EventType          string          `json:"eventType"`
	ToolName           string          `json:"toolName"`
	ToolArgs           map[string]any  `json:"toolArgs"`
	ToolResult         json.RawMessage `json:"toolResult,omitempty"`
	CallID             string          `json:"callId,omitempty"`
	Diff               string          `json:"diff,omitempty"`
	Paths              []string        `json:"paths,omitempty"`
	CheckpointID       *string         `json:"checkpointId,omitempty"`
	Changed            *bool           `json:"changed,omitempty"`
	Message            string          `json:"message,omitempty"`
	OutputFilter       map[string]any  `json:"outputFilter,omitempty"`
	OriginalSize       *int            `json:"originalSize,omitempty"`
	FilteredSize       *int            `json:"filteredSize,omitempty"`
	IterationIndex     *int            `json:"iterationIndex,omitempty"`
	IterationCap       *int            `json:"iterationCap,omitempty"`
	AuthorConnectionID string          `json:"authorConnectionId,omitempty"`
	AuthorDisplayName  string          `json:"authorDisplayName,omitempty"`
	AuthorRole         string          `json:"authorRole,omitempty"`
}

type CostUpdate struct {
	RequestID                string  `json:"requestId"`
	InputTokens              int     `json:"inputTokens"`
	OutputTokens             int     `json:"outputTokens"`
	EstimatedCost            float64 `json:"estimatedCost"`
	ModelName                string  `json:"modelName,omitempty"`
	CacheReadTokens          *int    `json:"cacheReadTokens,omitempty"`
	CacheWriteTokens         *int    `json:"cacheWriteTokens,omitempty"`
	CacheCreationInputTokens *int    `json:"cacheCreationInputTokens,omitempty"`
	CacheReadInputTokens     *int    `json:"cacheReadInputTokens,omitempty"`
	CumulativeInputTokens    *int    `json:"cumulativeInputTokens,omitempty"`
	CumulativeOutputTokens   *int    `json:"cumulativeOutputTokens,omitempty"`
	SystemTokens             *int    `json:"systemTokens,omitempty"`
	HistoryTokens            *int    `json:"historyTokens,omitempty"`
	ToolResultTokens         *int    `json:"toolResultTokens,omitempty"`
	IsEstimate               *bool   `json:"isEstimate,omitempty"`
	ConfidencePercent        *int    `json:"confidencePercent,omitempty"`
	ConfidenceCategory       string  `json:"confidenceCategory,omitempty"`
	AuthorConnectionID       string  `json:"authorConnectionId,omitempty"`
	AuthorDisplayName        string  `json:"authorDisplayName,omitempty"`
	AuthorRole               string  `json:"authorRole,omitempty"`
}

type Progress struct {
	RequestID          string `json:"requestId,omitempty"`
	Phase              string `json:"phase"`
	Message            string `json:"message"`
	IterationIndex     *int   `json:"iterationIndex,omitempty"`
	IterationCap       *int   `json:"iterationCap,omitempty"`
	AuthorConnectionID string `json:"authorConnectionId,omitempty"`
	AuthorDisplayName  string `json:"authorDisplayName,omitempty"`
	AuthorRole         string `json:"authorRole,omitempty"`
}

type PermissionReq struct {
	RequestID     string         `json:"requestId"`
	RequestKey    string         `json:"requestKey,omitempty"`
	PromptID      string         `json:"promptId,omitempty"`
	ToolName      string         `json:"toolName"`
	ToolArgs      map[string]any `json:"toolArgs,omitempty"`
	Description   string         `json:"description,omitempty"`
	Details       map[string]any `json:"details,omitempty"`
	Rationale     string         `json:"rationale,omitempty"`
	Operation     string         `json:"operation,omitempty"`
	Paths         []string       `json:"paths,omitempty"`
	Diff          string         `json:"diff,omitempty"`
	CheckpointID  *string        `json:"checkpointId,omitempty"`
	Changed       *bool          `json:"changed,omitempty"`
	Message       string         `json:"message,omitempty"`
	Capabilities  map[string]any `json:"capabilities,omitempty"`
	SandboxPreset string         `json:"sandboxPreset,omitempty"`
}

type PermissionRes struct {
	RequestID      string           `json:"requestId,omitempty"`
	RequestKey     string           `json:"requestKey,omitempty"`
	PromptID       string           `json:"promptId,omitempty"`
	Decision       string           `json:"decision,omitempty"`
	Allowed        *bool            `json:"allowed,omitempty"`
	RememberScope  string           `json:"rememberScope,omitempty"`
	ApprovedPaths  []string         `json:"approvedPaths,omitempty"`
	ApprovedChunks []map[string]any `json:"approvedChunks,omitempty"`
}

type ToolChunk struct {
	EventID    string `json:"eventId"`
	TurnID     string `json:"turnId,omitempty"`
	RequestID  string `json:"requestId,omitempty"`
	ToolCallID string `json:"toolCallId"`
	ToolName   string `json:"toolName"`
	ChunkIndex *int   `json:"chunkIndex,omitempty"`
	Chunk      string `json:"chunk"`
	TaskID     string `json:"taskId,omitempty"`
	SourceID   string `json:"sourceId,omitempty"`
}

type InlineChunk struct {
	RequestID string `json:"requestId"`
	Chunk     string `json:"chunk"`
	Done      bool   `json:"done"`
}

type SetTypingParams struct {
	Typing bool `json:"typing"`
}
