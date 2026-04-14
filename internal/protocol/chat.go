package protocol

type ChatParams struct {
	Message             string   `json:"message"`
	ContextFiles        []string `json:"contextFiles,omitempty"`
	PinnedContextFiles  []string `json:"pinnedContextFiles,omitempty"`
	ContextBudgetTokens *int     `json:"contextBudgetTokens,omitempty"`
	RequestID           string   `json:"requestId,omitempty"`
	SessionID           string   `json:"sessionId,omitempty"`
}

type ChatStreamingParams struct {
	Message             string   `json:"message"`
	ContextFiles        []string `json:"contextFiles,omitempty"`
	PinnedContextFiles  []string `json:"pinnedContextFiles,omitempty"`
	ContextBudgetTokens *int     `json:"contextBudgetTokens,omitempty"`
	MaxResponseTokens   *int     `json:"maxResponseTokens,omitempty"`
	RequestID           string   `json:"requestId,omitempty"`
	EditTurnID          string   `json:"editTurnId,omitempty"`
	SessionID           string   `json:"sessionId,omitempty"`
}

type ChatResult struct {
	Content string `json:"content"`
	Role    string `json:"role"`
}
