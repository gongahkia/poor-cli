package flows

import (
	"context"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

const usersToastTTL = 3 * time.Second

type UsersFlow struct {
	rpc    RPCClient
	state  StateDispatcher
	store  *state.Store
	unsubs []func()
	now    func() time.Time
}

type RolePicker struct {
	Member   state.Member
	Roles    []string
	Selected int
}

type UserRoleSelectedMsg struct {
	Member state.Member
	Role   string
}

func NewUsersFlow(d Deps) *UsersFlow {
	f := &UsersFlow{rpc: d.RPC, state: d.State, store: d.Store, now: d.Now}
	if f.state == nil && d.Store != nil {
		f.state = d.Store
	}
	if f.now == nil {
		f.now = time.Now
	}
	return f
}

func NewRolePicker(member state.Member) *RolePicker {
	selected := 0
	roles := []string{"viewer", "prompter"}
	for i, role := range roles {
		if role == member.Role {
			selected = i
			break
		}
	}
	return &RolePicker{Member: member, Roles: roles, Selected: selected}
}

func (f *UsersFlow) Name() string { return "users" }

func (f *UsersFlow) StartFlow(context.Context, Deps) error {
	sub, ok := f.rpc.(NotificationSubscriber)
	if !ok {
		return nil
	}
	f.unsubs = append(f.unsubs,
		sub.Subscribe(protocol.MethodMemberTyping, f.onMemberTyping),
		sub.Subscribe(protocol.MethodQueueUpdated, f.onQueueUpdated),
		sub.Subscribe(protocol.MethodCollabMemberJoin, func(any) { go f.refresh() }),
		sub.Subscribe(protocol.MethodCollabMemberLeft, func(any) { go f.refresh() }),
	)
	return nil
}

func (f *UsersFlow) Stop() error {
	for _, unsub := range f.unsubs {
		if unsub != nil {
			unsub()
		}
	}
	f.unsubs = nil
	return nil
}

func (f *UsersFlow) Update(tea.Msg) tea.Cmd { return nil }

func (f *UsersFlow) RefreshCmd() tea.Cmd {
	return func() tea.Msg {
		f.refresh()
		return nil
	}
}

func (f *UsersFlow) Approve(member state.Member) tea.Cmd {
	return f.memberAction("approve", protocol.MethodApproveHostMember, member, "")
}

func (f *UsersFlow) Deny(member state.Member) tea.Cmd {
	return f.memberAction("deny", protocol.MethodDenyHostMember, member, "")
}

func (f *UsersFlow) Kick(member state.Member) tea.Cmd {
	return f.memberAction("kick", protocol.MethodRemoveHostMember, member, "")
}

func (f *UsersFlow) Pass(member state.Member) tea.Cmd {
	return f.memberAction("pass", protocol.MethodHandoffHostMember, member, "")
}

func (f *UsersFlow) SetRole(member state.Member, role string) tea.Cmd {
	return f.memberAction("role", protocol.MethodSetHostMemberRole, member, role)
}

func (f *UsersFlow) memberAction(label, method string, member state.Member, role string) tea.Cmd {
	return func() tea.Msg {
		if strings.TrimSpace(member.ConnectionID) == "" {
			f.toast(state.ToastWarning, "no user selected")
			return nil
		}
		params := protocol.MemberActionParams{Room: f.roomName(), ConnectionID: member.ConnectionID, Role: role}
		var result protocol.MemberActionResult
		if err := callRPC(f.rpc, method, params, &result); err != nil {
			f.toast(state.ToastError, fmt.Sprintf("%s failed: %v", label, err))
			return nil
		}
		if result.Error != "" {
			f.toast(state.ToastError, fmt.Sprintf("%s failed: %s", label, result.Error))
			return nil
		}
		f.toast(state.ToastSuccess, label+" ok")
		f.refresh()
		return nil
	}
}

func (f *UsersFlow) onMemberTyping(params any) {
	var msg protocol.MemberTypingNotification
	if !decodeNotification(params, &msg) {
		return
	}
	connectionID := firstNonEmptyString(msg.ConnectionID, msg.ConnectionIDAlt)
	if connectionID == "" {
		return
	}
	f.dispatch(state.ActionUpdateMemberTyping{
		ConnectionID: connectionID,
		DisplayName:  firstNonEmptyString(msg.DisplayName, msg.DisplayNameAlt),
		Typing:       msg.Typing,
		At:           f.now(),
	})
}

func (f *UsersFlow) onQueueUpdated(params any) {
	var msg protocol.QueueUpdatedNotification
	if !decodeNotification(params, &msg) {
		return
	}
	f.dispatch(state.ActionUpdateQueue{Queue: stateQueueItems(queueItems(msg.Snapshot, msg.Queue, msg.Items))})
}

func (f *UsersFlow) refresh() {
	if f.rpc == nil {
		return
	}
	room := f.roomName()
	params := map[string]string{}
	if room != "" {
		params["room"] = room
	}
	var host protocol.HostMembersResult
	if err := callRPC(f.rpc, protocol.MethodListHostMembers, params, &host); err != nil {
		f.toast(state.ToastError, fmt.Sprintf("users failed: %v", err))
		return
	}
	base := f.multiplayer()
	mp := multiplayerFromHost(host, room)
	mp.LocalConnectionID = base.LocalConnectionID
	mp.LocalDisplayName = base.LocalDisplayName
	mp.HunkVotes = base.HunkVotes
	var presence protocol.PresenceResult
	if err := callRPC(f.rpc, protocol.MethodListPresence, params, &presence); err == nil {
		mergePresence(&mp, presence)
	}
	var queue protocol.RoomQueueResult
	if err := callRPC(f.rpc, protocol.MethodListRoomQueue, params, &queue); err == nil {
		mp.Queue = stateQueueItems(queueItems(queue.Snapshot, queue.Queue, queue.Items))
		mergeQueue(&mp)
	}
	f.dispatch(state.ActionSetMultiplayer{Multiplayer: mp})
}

func (f *UsersFlow) roomName() string {
	return f.multiplayer().RoomName
}

func (f *UsersFlow) multiplayer() state.MultiplayerState {
	if f.store == nil {
		return state.MultiplayerState{}
	}
	return f.store.Snapshot().Multiplayer
}

func (f *UsersFlow) toast(kind state.ToastKind, text string) {
	f.dispatch(state.ActionToast{Kind: kind, Text: text, TTL: usersToastTTL})
}

func (f *UsersFlow) dispatch(action state.Action) {
	if f.state != nil {
		f.state.Dispatch(action)
	}
}

func (p *RolePicker) Update(msg tea.KeyMsg) tea.Cmd {
	switch msg.String() {
	case "up", "ctrl+p":
		if p.Selected > 0 {
			p.Selected--
		}
	case "down", "ctrl+n":
		if p.Selected < len(p.Roles)-1 {
			p.Selected++
		}
	case "enter":
		if len(p.Roles) == 0 {
			return nil
		}
		return emitCommand(UserRoleSelectedMsg{Member: p.Member, Role: p.Roles[p.Selected]})
	}
	return nil
}

func (p *RolePicker) View(width, height int) string {
	lines := make([]string, 0, len(p.Roles)+1)
	lines = append(lines, "role for "+firstNonEmptyString(p.Member.DisplayName, p.Member.ConnectionID))
	for i, role := range p.Roles {
		marker := " "
		if i == p.Selected {
			marker = "›"
		}
		lines = append(lines, marker+" "+role)
	}
	if height > 0 && len(lines) > height {
		lines = lines[:height]
	}
	return strings.Join(lines, "\n")
}

func multiplayerFromHost(host protocol.HostMembersResult, wantedRoom string) state.MultiplayerState {
	room := pickRoom(host, wantedRoom)
	roomName := firstNonEmptyString(room.Name, room.Room, wantedRoom)
	members := make([]state.Member, 0, len(room.Members))
	for _, member := range room.Members {
		members = append(members, stateMember(member))
	}
	return state.MultiplayerState{
		Enabled:  host.Running || len(members) > 0,
		RoomName: roomName,
		Members:  members,
		Typing:   map[string]bool{},
	}
}

func pickRoom(host protocol.HostMembersResult, wanted string) protocol.RoomSnapshot {
	if host.Room.Name != "" || host.Room.Room != "" || len(host.Room.Members) > 0 {
		return host.Room
	}
	if wanted != "" {
		for _, room := range host.Rooms {
			if room.Name == wanted || room.Room == wanted {
				return room
			}
		}
	}
	if len(host.Rooms) > 0 {
		return host.Rooms[0]
	}
	return protocol.RoomSnapshot{}
}

func mergePresence(mp *state.MultiplayerState, presence protocol.PresenceResult) {
	if mp.Typing == nil {
		mp.Typing = map[string]bool{}
	}
	for id, typing := range presence.Presence {
		mp.Typing[id] = typing
	}
	for _, member := range presence.Members {
		next := stateMember(member)
		if next.ConnectionID == "" {
			continue
		}
		mp.Typing[next.ConnectionID] = member.Typing
		idx := memberIndex(mp.Members, next.ConnectionID)
		if idx >= 0 {
			if next.DisplayName != "" {
				mp.Members[idx].DisplayName = next.DisplayName
			}
			continue
		}
		mp.Members = append(mp.Members, next)
	}
	if presence.Room != "" {
		mp.RoomName = presence.Room
	}
	mp.Enabled = mp.Enabled || len(mp.Members) > 0
	mp.PresenceAt = time.Now()
}

func mergeQueue(mp *state.MultiplayerState) {
	positions := map[string]int{}
	for _, item := range mp.Queue {
		positions[item.ConnectionID] = item.Position
	}
	for i := range mp.Members {
		mp.Members[i].QueuePosition = positions[mp.Members[i].ConnectionID]
	}
}

func stateMember(member protocol.MultiplayerMember) state.Member {
	approvedState := firstNonEmptyString(member.ApprovalState, member.ApprovalAlt)
	if approvedState == "" && member.Approved != nil {
		if *member.Approved {
			approvedState = "approved"
		} else {
			approvedState = "pending"
		}
	}
	return state.Member{
		ConnectionID:  firstNonEmptyString(member.ConnectionID, member.ConnectionIDAlt),
		DisplayName:   firstNonEmptyString(member.DisplayName, member.DisplayNameAlt, member.ClientName, member.ClientNameAlt, member.Name),
		Role:          firstNonEmptyString(member.Role, "viewer"),
		ApprovalState: approvedState,
		HandRaised:    member.HandRaised || member.HandRaisedAlt,
		QueuePosition: firstNonZeroInt(member.QueuePosition, member.QueuePosAlt),
		VotesCast:     firstNonZeroInt(member.VotesCast, member.VotesCastAlt),
		VotesPending:  firstNonZeroInt(member.VotesPending, member.VotesPendingAlt),
	}
}

func queueItems(groups ...[]protocol.QueueItem) []protocol.QueueItem {
	for _, group := range groups {
		if len(group) > 0 {
			return group
		}
	}
	return nil
}

func stateQueueItems(items []protocol.QueueItem) []state.QueueItem {
	out := make([]state.QueueItem, 0, len(items))
	for _, item := range items {
		connectionID := firstNonEmptyString(item.ConnectionID, item.ConnectionIDAlt, item.ID)
		if connectionID == "" {
			continue
		}
		out = append(out, state.QueueItem{
			ConnectionID: connectionID,
			Position:     firstNonZeroInt(item.Position, item.QueuePosition, item.QueuePosAlt),
		})
	}
	return out
}

func memberIndex(members []state.Member, connectionID string) int {
	for i := range members {
		if members[i].ConnectionID == connectionID {
			return i
		}
	}
	return -1
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func firstNonZeroInt(values ...int) int {
	for _, value := range values {
		if value != 0 {
			return value
		}
	}
	return 0
}
