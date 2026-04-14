package protocol

type DiffListParams struct{}

type DiffListResult struct {
	Edits []DiffPreview `json:"edits"`
}

type DiffPreviewParams struct {
	EditID string `json:"editId"`
}

type DiffPreview struct {
	EditIDLegacy       string       `json:"edit_id,omitempty"`
	EditID             string       `json:"editId"`
	Path               string       `json:"path"`
	Prompt             string       `json:"prompt,omitempty"`
	ToolCallIDLegacy   string       `json:"tool_call_id,omitempty"`
	ToolCallID         string       `json:"toolCallId,omitempty"`
	Status             string       `json:"status,omitempty"`
	Diff               string       `json:"diff,omitempty"`
	Original           string       `json:"original,omitempty"`
	Proposed           string       `json:"proposed,omitempty"`
	Hunks              []HunkDetail `json:"hunks"`
	CheckpointIDLegacy *string      `json:"checkpoint_id,omitempty"`
	CheckpointID       *string      `json:"checkpointId,omitempty"`
	Finalized          bool         `json:"finalized,omitempty"`
}

type PendingEdit = DiffPreview

type HunkDetail struct {
	HunkIDLegacy string `json:"hunk_id,omitempty"`
	HunkID       string `json:"hunkId"`
	Path         string `json:"path,omitempty"`
	Header       string `json:"header"`
	Before       string `json:"before,omitempty"`
	After        string `json:"after,omitempty"`
	LineStartRaw int    `json:"line_start,omitempty"`
	LineStart    int    `json:"lineStart,omitempty"`
	Status       string `json:"status,omitempty"`
	Body         string `json:"body,omitempty"`
	Added        int    `json:"added,omitempty"`
	Removed      int    `json:"removed,omitempty"`
}

type Hunk = HunkDetail

type DiffStageParams struct {
	Path       string `json:"path"`
	Original   string `json:"original,omitempty"`
	Proposed   string `json:"proposed,omitempty"`
	ToolCallID string `json:"toolCallId,omitempty"`
	Prompt     string `json:"prompt,omitempty"`
}

type DiffStageResult = DiffPreview

type AcceptParams struct {
	EditID string `json:"editId"`
	HunkID string `json:"hunkId,omitempty"`
}

type RejectParams struct {
	EditID string `json:"editId"`
	HunkID string `json:"hunkId,omitempty"`
}

type RegenParams struct {
	EditID      string `json:"editId"`
	HunkID      string `json:"hunkId"`
	Instruction string `json:"instruction,omitempty"`
	NewContent  string `json:"newContent,omitempty"`
}
