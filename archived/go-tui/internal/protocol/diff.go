package protocol

import (
	"encoding/json"
	"sort"
)

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
	HunkIDLegacy        string    `json:"hunk_id,omitempty"`
	HunkID              string    `json:"hunkId"`
	Path                string    `json:"path,omitempty"`
	Header              string    `json:"header"`
	Before              string    `json:"before,omitempty"`
	After               string    `json:"after,omitempty"`
	LineStartRaw        int       `json:"line_start,omitempty"`
	LineStart           int       `json:"lineStart,omitempty"`
	Status              string    `json:"status,omitempty"`
	SafetyClass         string    `json:"safetyClass,omitempty"`
	Body                string    `json:"body,omitempty"`
	Added               int       `json:"added,omitempty"`
	Removed             int       `json:"removed,omitempty"`
	Votes               HunkVotes `json:"votes,omitempty"`
	VoteStatus          string    `json:"voteStatus,omitempty"`
	VoteStatusLegacy    string    `json:"vote_status,omitempty"`
	VotingStatus        string    `json:"votingStatus,omitempty"`
	VotingStatusLegacy  string    `json:"voting_status,omitempty"`
	VoteThreshold       string    `json:"voteThreshold,omitempty"`
	VoteThresholdLegacy string    `json:"vote_threshold,omitempty"`
	Threshold           string    `json:"threshold,omitempty"`
	RequiredVoters      int       `json:"requiredVoters,omitempty"`
	RequiredVotersRaw   int       `json:"required_voters,omitempty"`
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

type HunkVote struct {
	ConnectionID       string  `json:"connectionId,omitempty"`
	ConnectionIDLegacy string  `json:"connection_id,omitempty"`
	DisplayName        string  `json:"displayName,omitempty"`
	DisplayNameLegacy  string  `json:"display_name,omitempty"`
	Name               string  `json:"name,omitempty"`
	Decision           string  `json:"decision,omitempty"`
	Vote               string  `json:"vote,omitempty"`
	At                 float64 `json:"at,omitempty"`
}

type HunkVotes []HunkVote

func (v *HunkVotes) UnmarshalJSON(data []byte) error {
	var rows []HunkVote
	if err := json.Unmarshal(data, &rows); err == nil {
		*v = rows
		return nil
	}
	var keyed map[string]HunkVote
	if err := json.Unmarshal(data, &keyed); err != nil {
		return err
	}
	keys := make([]string, 0, len(keyed))
	for key := range keyed {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	rows = make([]HunkVote, 0, len(keys))
	for _, key := range keys {
		vote := keyed[key]
		if vote.ConnectionID == "" && vote.ConnectionIDLegacy == "" {
			vote.ConnectionID = key
		}
		rows = append(rows, vote)
	}
	*v = rows
	return nil
}

type HunkVoteParams struct {
	EditID   string `json:"editId,omitempty"`
	HunkID   string `json:"hunkId"`
	Decision string `json:"decision"`
}

type HunkVoteUpdate struct {
	EditID              string    `json:"editId,omitempty"`
	EditIDLegacy        string    `json:"edit_id,omitempty"`
	HunkID              string    `json:"hunkId"`
	HunkIDLegacy        string    `json:"hunk_id,omitempty"`
	Votes               HunkVotes `json:"votes,omitempty"`
	Status              string    `json:"status,omitempty"`
	VoteStatus          string    `json:"voteStatus,omitempty"`
	VoteStatusLegacy    string    `json:"vote_status,omitempty"`
	Threshold           string    `json:"threshold,omitempty"`
	VoteThreshold       string    `json:"voteThreshold,omitempty"`
	VoteThresholdLegacy string    `json:"vote_threshold,omitempty"`
	RequiredVoters      int       `json:"requiredVoters,omitempty"`
	RequiredVotersRaw   int       `json:"required_voters,omitempty"`
}
