package protocol

type TimelineEvent struct {
	EventID        string         `json:"eventId"`
	TurnID         string         `json:"turnId"`
	ToolCallID     string         `json:"toolCallId"`
	ToolName       string         `json:"toolName"`
	Status         string         `json:"status"`
	ArgsPreview    string         `json:"argsPreview,omitempty"`
	ArgsFull       map[string]any `json:"argsFull,omitempty"`
	StartedAt      *float64       `json:"startedAt,omitempty"`
	EndedAt        *float64       `json:"endedAt,omitempty"`
	DurationMs     *int           `json:"durationMs,omitempty"`
	ResultPreview  string         `json:"resultPreview,omitempty"`
	ResultFull     string         `json:"resultFull,omitempty"`
	ResultFullSize int            `json:"resultFullSize,omitempty"`
	Error          *string        `json:"error,omitempty"`
	CostTokens     *int           `json:"costTokens,omitempty"`
	StreamChunks   []string       `json:"streamChunks,omitempty"`
	Dismissed      bool           `json:"dismissed,omitempty"`
	UpdatedAt      float64        `json:"updatedAt,omitempty"`
	ID             string         `json:"id,omitempty"`
	Type           string         `json:"type,omitempty"`
	Payload        map[string]any `json:"payload,omitempty"`
}

type TimelineListParams struct {
	TurnID string `json:"turnId,omitempty"`
	Limit  *int   `json:"limit,omitempty"`
}

type TimelineListResult struct {
	Events []TimelineEvent `json:"events"`
}

type CancelEventParams struct {
	EventID string `json:"eventId"`
}

type RetryEventParams struct {
	EventID string `json:"eventId"`
}

type DismissEventParams struct {
	EventID string `json:"eventId"`
}

type TimelineCancelResult struct {
	Cancelled bool `json:"cancelled"`
}

type TimelineRetryResult struct {
	NewEventID string `json:"newEventId"`
	OK         bool   `json:"ok"`
	Error      string `json:"error,omitempty"`
}

type TimelineDismissResult struct {
	OK bool `json:"ok"`
}
