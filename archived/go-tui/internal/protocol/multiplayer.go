package protocol

type HostMembersResult struct {
	Running bool           `json:"running"`
	Room    RoomSnapshot   `json:"room,omitempty"`
	Rooms   []RoomSnapshot `json:"rooms,omitempty"`
}

type RoomSnapshot struct {
	Name               string              `json:"name,omitempty"`
	Room               string              `json:"room,omitempty"`
	Members            []MultiplayerMember `json:"members,omitempty"`
	MemberCount        int                 `json:"memberCount,omitempty"`
	ActiveConnectionID string              `json:"activeConnectionId,omitempty"`
	QueueDepth         int                 `json:"queueDepth,omitempty"`
}

type MultiplayerMember struct {
	ConnectionID    string `json:"connectionId,omitempty"`
	ConnectionIDAlt string `json:"connection_id,omitempty"`
	DisplayName     string `json:"displayName,omitempty"`
	DisplayNameAlt  string `json:"display_name,omitempty"`
	ClientName      string `json:"clientName,omitempty"`
	ClientNameAlt   string `json:"client_name,omitempty"`
	Name            string `json:"name,omitempty"`
	Role            string `json:"role,omitempty"`
	ApprovalState   string `json:"approvalState,omitempty"`
	ApprovalAlt     string `json:"approval_state,omitempty"`
	Approved        *bool  `json:"approved,omitempty"`
	HandRaised      bool   `json:"handRaised,omitempty"`
	HandRaisedAlt   bool   `json:"hand_raised,omitempty"`
	QueuePosition   int    `json:"queuePosition,omitempty"`
	QueuePosAlt     int    `json:"queue_position,omitempty"`
	VotesCast       int    `json:"votesCast,omitempty"`
	VotesCastAlt    int    `json:"votes_cast,omitempty"`
	VotesPending    int    `json:"votesPending,omitempty"`
	VotesPendingAlt int    `json:"votes_pending,omitempty"`
	Typing          bool   `json:"typing,omitempty"`
}

type PresenceResult struct {
	Room     string              `json:"room,omitempty"`
	Presence map[string]bool     `json:"presence,omitempty"`
	Members  []MultiplayerMember `json:"members,omitempty"`
}

type RoomQueueResult struct {
	Room     string      `json:"room,omitempty"`
	Snapshot []QueueItem `json:"snapshot,omitempty"`
	Queue    []QueueItem `json:"queue,omitempty"`
	Items    []QueueItem `json:"items,omitempty"`
}

type QueueItem struct {
	ConnectionID    string `json:"connectionId,omitempty"`
	ConnectionIDAlt string `json:"connection_id,omitempty"`
	ID              string `json:"id,omitempty"`
	Position        int    `json:"position,omitempty"`
	QueuePosition   int    `json:"queuePosition,omitempty"`
	QueuePosAlt     int    `json:"queue_position,omitempty"`
}

type MemberTypingNotification struct {
	Room            string `json:"room,omitempty"`
	ConnectionID    string `json:"connectionId,omitempty"`
	ConnectionIDAlt string `json:"connection_id,omitempty"`
	DisplayName     string `json:"displayName,omitempty"`
	DisplayNameAlt  string `json:"display_name,omitempty"`
	Typing          bool   `json:"typing"`
}

type QueueUpdatedNotification struct {
	Room     string      `json:"room,omitempty"`
	RoomID   string      `json:"roomId,omitempty"`
	Snapshot []QueueItem `json:"snapshot,omitempty"`
	Queue    []QueueItem `json:"queue,omitempty"`
	Items    []QueueItem `json:"items,omitempty"`
}

type MemberActionParams struct {
	Room         string `json:"room,omitempty"`
	ConnectionID string `json:"connectionId,omitempty"`
	Role         string `json:"role,omitempty"`
}

type MemberActionResult struct {
	Success      bool   `json:"success,omitempty"`
	Room         string `json:"room,omitempty"`
	ConnectionID string `json:"connectionId,omitempty"`
	Role         string `json:"role,omitempty"`
	Error        string `json:"error,omitempty"`
}
