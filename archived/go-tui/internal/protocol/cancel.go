package protocol

type CancelParams struct {
	RequestID string `json:"requestId"`
}

type CancelResult struct {
	Success   bool   `json:"success"`
	RequestID string `json:"requestId,omitempty"`
}
