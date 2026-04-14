package protocol

type SessionSummary struct {
	SessionID        string  `json:"sessionId"`
	StartedAt        string  `json:"startedAt,omitempty"`
	EndedAt          *string `json:"endedAt,omitempty"`
	Model            string  `json:"model,omitempty"`
	MessageCount     int     `json:"messageCount"`
	IsActive         bool    `json:"isActive,omitempty"`
	Source           string  `json:"source,omitempty"`
	Label            string  `json:"label,omitempty"`
	WorkingDirectory string  `json:"workingDirectory,omitempty"`
	Status           string  `json:"status,omitempty"`
	CreatedAt        string  `json:"createdAt,omitempty"`
	BranchName       string  `json:"branchName,omitempty"`
	IsDefault        bool    `json:"isDefault,omitempty"`
	Title            string  `json:"title,omitempty"`
	CostUSD          float64 `json:"costUsd,omitempty"`
	UpdatedAt        int64   `json:"updatedAt,omitempty"`
	ID               string  `json:"id,omitempty"`
}

type ListSessionsResult struct {
	Sessions        []SessionSummary `json:"sessions"`
	ActiveSessionID string           `json:"activeSessionId,omitempty"`
}

type SwitchSessionParams struct {
	SessionID string `json:"sessionId"`
}

type SwitchSessionResult struct {
	Session SessionSummary `json:"session,omitempty"`
	Error   string         `json:"error,omitempty"`
}

type Checkpoint struct {
	CheckpointID   string   `json:"checkpointId"`
	CreatedAt      string   `json:"createdAt"`
	Description    string   `json:"description"`
	OperationType  string   `json:"operationType"`
	FileCount      int      `json:"fileCount"`
	TotalSizeBytes int      `json:"totalSizeBytes"`
	Tags           []string `json:"tags,omitempty"`
}

type ListCheckpointsResult struct {
	Available        bool         `json:"available"`
	Checkpoints      []Checkpoint `json:"checkpoints"`
	StorageSizeBytes int          `json:"storageSizeBytes"`
	StoragePath      string       `json:"storagePath"`
}
