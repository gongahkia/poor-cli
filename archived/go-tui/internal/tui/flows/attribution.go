package flows

import "github.com/gongahkia/gocli-poor/internal/state"

type authorFields struct {
	ConnectionID string
	DisplayName  string
	Role         string
}

func (a authorFields) empty() bool {
	return a.ConnectionID == "" && a.DisplayName == "" && a.Role == ""
}

func authorAction(requestID string, a authorFields) state.ActionSetMessageAuthor {
	return state.ActionSetMessageAuthor{
		RequestID:          requestID,
		AuthorConnectionID: a.ConnectionID,
		AuthorDisplayName:  a.DisplayName,
		AuthorRole:         a.Role,
	}
}
