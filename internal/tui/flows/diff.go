package flows

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

var ErrNoPendingEdits = errors.New("diff: no pending edits")

const diffVoteToastTTL = 3 * time.Second

type Caller interface {
	Call(ctx context.Context, method string, params any, result any) error
}

type DiffReviewFlow struct {
	rpc                 Caller
	autoAcceptSafeEdits bool
	edits               []protocol.PendingEdit
	selectedEdit        int
	selectedHunk        int
	scroll              int
	regenInput          string
	regenMode           bool
	open                bool
	state               StateDispatcher
	theme               *theme.Theme
	voteToastKey        string
}

type DiffReviewModal struct {
	Flow   *DiffReviewFlow
	Width  int
	Height int
}

func NewDiffReviewFlow(rpc Caller, autoAcceptSafeEdits bool) *DiffReviewFlow {
	return &DiffReviewFlow{rpc: rpc, autoAcceptSafeEdits: autoAcceptSafeEdits}
}

func (f *DiffReviewFlow) SetStateDispatcher(state StateDispatcher) {
	f.state = state
}

func (f *DiffReviewFlow) SetTheme(tm *theme.Theme) {
	f.theme = tm
}

func (f *DiffReviewFlow) Open(ctx context.Context) error {
	if err := f.fetch(ctx); err != nil {
		return err
	}
	if len(f.edits) == 0 {
		f.open = false
		return ErrNoPendingEdits
	}
	f.open = true
	f.selectedEdit = clamp(f.selectedEdit, 0, len(f.edits)-1)
	f.selectedHunk = clamp(f.selectedHunk, 0, len(f.edits[f.selectedEdit].Hunks)-1)
	f.scroll = 0
	return f.previewCurrentIfNeeded(ctx)
}

func (f *DiffReviewFlow) OnEditsReady(ctx context.Context) (bool, error) {
	if err := f.fetch(ctx); err != nil {
		return false, err
	}
	if len(f.edits) == 0 {
		f.open = false
		return false, nil
	}
	if !f.autoAcceptSafeEdits {
		f.open = true
		return true, nil
	}
	if allEditsSafe(f.edits) {
		if err := f.call(ctx, protocol.MethodAcceptAll, nil, nil); err != nil {
			return false, err
		}
		f.open = false
		f.edits = nil
		return false, nil
	}
	accepted := false
	for _, edit := range f.edits {
		if !editSafe(edit) {
			continue
		}
		editID := normalizedEditID(edit)
		for _, hunk := range edit.Hunks {
			if err := f.call(ctx, protocol.MethodAcceptHunk, protocol.AcceptParams{EditID: editID, HunkID: normalizedHunkID(hunk)}, nil); err != nil {
				return false, err
			}
			accepted = true
		}
	}
	if accepted {
		if err := f.fetch(ctx); err != nil {
			return false, err
		}
	}
	f.open = len(f.edits) > 0
	return f.open, nil
}

func (f *DiffReviewFlow) HandleKey(ctx context.Context, key string) error {
	if f.regenMode {
		return f.handleRegenKey(ctx, key)
	}
	switch key {
	case "y":
		if f.blockedByVote("approved") {
			f.toastVoteBlocked()
			return nil
		}
		return f.AcceptHunk(ctx)
	case "n":
		if f.blockedByVote("rejected") {
			f.toastVoteBlocked()
			return nil
		}
		return f.RejectHunk(ctx)
	case "va":
		return f.VoteHunk(ctx, "approve")
	case "vr":
		return f.VoteHunk(ctx, "reject")
	case "vc":
		return f.VoteHunk(ctx, "clear")
	case "r":
		f.regenMode = true
		f.regenInput = ""
	case "Y":
		return f.AcceptAll(ctx)
	case "N":
		return f.RejectAll(ctx)
	case "up", "k":
		f.selectHunk(f.selectedHunk - 1)
	case "down", "j":
		f.selectHunk(f.selectedHunk + 1)
	case "left", "h":
		f.selectEdit(f.selectedEdit - 1)
		return f.previewCurrentIfNeeded(ctx)
	case "right", "l":
		f.selectEdit(f.selectedEdit + 1)
		return f.previewCurrentIfNeeded(ctx)
	case "pgup":
		f.Scroll(-12)
	case "pgdown":
		f.Scroll(12)
	case "home":
		f.scroll = 0
	case "end":
		f.scroll = 1 << 30
	}
	return nil
}

func (f *DiffReviewFlow) AcceptHunk(ctx context.Context) error {
	edit, hunk, ok := f.current()
	if !ok {
		return ErrNoPendingEdits
	}
	if err := f.call(ctx, protocol.MethodAcceptHunk, protocol.AcceptParams{EditID: normalizedEditID(edit), HunkID: normalizedHunkID(hunk)}, nil); err != nil {
		return err
	}
	f.dropCurrentHunk()
	return nil
}

func (f *DiffReviewFlow) RejectHunk(ctx context.Context) error {
	edit, hunk, ok := f.current()
	if !ok {
		return ErrNoPendingEdits
	}
	if err := f.call(ctx, protocol.MethodRejectHunk, protocol.RejectParams{EditID: normalizedEditID(edit), HunkID: normalizedHunkID(hunk)}, nil); err != nil {
		return err
	}
	f.dropCurrentHunk()
	return nil
}

func (f *DiffReviewFlow) RegenerateHunk(ctx context.Context, instruction string) error {
	edit, hunk, ok := f.current()
	if !ok {
		return ErrNoPendingEdits
	}
	params := protocol.RegenParams{EditID: normalizedEditID(edit), HunkID: normalizedHunkID(hunk), Instruction: strings.TrimSpace(instruction)}
	return f.call(ctx, protocol.MethodRegenerateHunk, params, nil)
}

func (f *DiffReviewFlow) VoteHunk(ctx context.Context, decision string) error {
	edit, hunk, ok := f.current()
	if !ok {
		return ErrNoPendingEdits
	}
	return VoteOnHunk(ctx, f.rpc, protocol.HunkVoteParams{EditID: normalizedEditID(edit), HunkID: normalizedHunkID(hunk), Decision: decision})
}

func (f *DiffReviewFlow) AcceptAll(ctx context.Context) error {
	if err := f.call(ctx, protocol.MethodAcceptAll, nil, nil); err != nil {
		return err
	}
	f.edits = nil
	f.open = false
	return nil
}

func (f *DiffReviewFlow) RejectAll(ctx context.Context) error {
	if err := f.call(ctx, protocol.MethodRejectAll, nil, nil); err != nil {
		return err
	}
	f.edits = nil
	f.open = false
	return nil
}

func (f *DiffReviewFlow) Scroll(delta int) {
	_, hunk, ok := f.current()
	if !ok {
		return
	}
	f.scroll = clamp(f.scroll+delta, 0, max(0, hunkLineCount(hunk)-1))
}

func (f *DiffReviewFlow) View(width, height int) string {
	return DiffReviewModal{Flow: f, Width: width, Height: height}.View()
}

func (f *DiffReviewFlow) Edits() []protocol.PendingEdit {
	out := make([]protocol.PendingEdit, len(f.edits))
	copy(out, f.edits)
	return out
}

func (f *DiffReviewFlow) Opened() bool {
	return f.open
}

func (m DiffReviewModal) View() string {
	width := max(20, m.Width)
	height := max(8, m.Height)
	body := "no pending edits"
	if m.Flow != nil && len(m.Flow.edits) > 0 {
		body = m.Flow.render(width-2, height-2)
	}
	return lipgloss.NewStyle().
		Width(width).
		Height(height).
		Border(lipgloss.NormalBorder()).
		Render(body)
}

func (f *DiffReviewFlow) render(width, height int) string {
	width = max(1, width)
	height = max(1, height)
	listHeight := clamp(len(f.edits)+1, 2, min(6, max(2, height/3)))
	lines := make([]string, 0, height)
	lines = append(lines, fit(fmt.Sprintf("Pending edits (%d)", len(f.edits)), width))
	for i := 0; i < listHeight-1; i++ {
		if i >= len(f.edits) {
			lines = append(lines, fit("", width))
			continue
		}
		edit := f.edits[i]
		marker := " "
		if i == f.selectedEdit {
			marker = ">"
		}
		added, removed := editStats(edit)
		lines = append(lines, fit(fmt.Sprintf("%s %s  +%d -%d", marker, edit.Path, added, removed), width))
	}
	edit, hunk, ok := f.current()
	if !ok {
		return strings.Join(lines, "\n")
	}
	lines = append(lines, fit("", width))
	lines = append(lines, fit(fmt.Sprintf("Diff: %s  hunk %d/%d", edit.Path, f.selectedHunk+1, len(edit.Hunks)), width))
	if row, ok := f.renderVoteRow(hunk, width); ok {
		lines = append(lines, row)
	}
	diffHeight := max(1, height-len(lines)-3)
	total := hunkLineCount(hunk)
	f.scroll = clamp(f.scroll, 0, max(0, total-1))
	lines = append(lines, renderHunkWindow(hunk, f.scroll, diffHeight, width)...)
	scrollText := fmt.Sprintf("scroll %d/%d", min(total, f.scroll+diffHeight), total)
	if total <= diffHeight {
		scrollText = "scroll all"
	}
	lines = append(lines, fit(scrollText, width))
	if f.regenMode {
		lines = append(lines, fit("regen instruction: "+f.regenInput, width))
	} else {
		lines = append(lines, fit("[y] accept hunk  [n] reject  [r] regen", width))
	}
	lines = append(lines, fit("[Y] accept all   [N] reject all", width))
	for len(lines) < height {
		lines = append(lines, fit("", width))
	}
	if len(lines) > height {
		lines = lines[:height]
	}
	return strings.Join(lines, "\n")
}

func (f *DiffReviewFlow) fetch(ctx context.Context) error {
	var result protocol.DiffListResult
	if err := f.call(ctx, protocol.MethodListPendingEdits, protocol.DiffListParams{}, &result); err != nil {
		return err
	}
	f.edits = result.Edits
	f.selectedEdit = clamp(f.selectedEdit, 0, max(0, len(f.edits)-1))
	f.selectedHunk = 0
	f.scroll = 0
	return nil
}

func (f *DiffReviewFlow) previewCurrentIfNeeded(ctx context.Context) error {
	if len(f.edits) == 0 {
		return nil
	}
	edit := f.edits[f.selectedEdit]
	if !editNeedsPreview(edit) {
		return nil
	}
	var preview protocol.DiffPreview
	if err := f.call(ctx, protocol.MethodPreviewEdit, protocol.DiffPreviewParams{EditID: normalizedEditID(edit)}, &preview); err != nil {
		return err
	}
	if preview.Path != "" || len(preview.Hunks) > 0 || preview.Diff != "" {
		f.edits[f.selectedEdit] = preview
		f.selectedHunk = clamp(f.selectedHunk, 0, max(0, len(preview.Hunks)-1))
	}
	return nil
}

func editNeedsPreview(edit protocol.PendingEdit) bool {
	if edit.Diff != "" {
		return false
	}
	for _, hunk := range edit.Hunks {
		if hunk.Body != "" || hunk.Before != "" || hunk.After != "" {
			return false
		}
	}
	return len(edit.Hunks) > 0
}

func (f *DiffReviewFlow) call(ctx context.Context, method string, params any, result any) error {
	if f.rpc == nil {
		return errors.New("diff: nil rpc")
	}
	return f.rpc.Call(ctx, method, params, result)
}

func (f *DiffReviewFlow) handleRegenKey(ctx context.Context, key string) error {
	switch key {
	case "enter":
		instruction := f.regenInput
		f.regenInput = ""
		f.regenMode = false
		return f.RegenerateHunk(ctx, instruction)
	case "esc":
		f.regenInput = ""
		f.regenMode = false
	case "backspace":
		if f.regenInput != "" {
			r := []rune(f.regenInput)
			f.regenInput = string(r[:len(r)-1])
		}
	default:
		f.regenInput += key
	}
	return nil
}

func (f *DiffReviewFlow) selectEdit(next int) {
	f.selectedEdit = clamp(next, 0, len(f.edits)-1)
	f.selectedHunk = 0
	f.scroll = 0
	f.voteToastKey = ""
}

func (f *DiffReviewFlow) selectHunk(next int) {
	if len(f.edits) == 0 {
		return
	}
	f.selectedHunk = clamp(next, 0, len(f.edits[f.selectedEdit].Hunks)-1)
	f.scroll = 0
	f.voteToastKey = ""
}

func (f *DiffReviewFlow) current() (protocol.PendingEdit, protocol.HunkDetail, bool) {
	if len(f.edits) == 0 || f.selectedEdit < 0 || f.selectedEdit >= len(f.edits) {
		return protocol.PendingEdit{}, protocol.HunkDetail{}, false
	}
	edit := f.edits[f.selectedEdit]
	if len(edit.Hunks) == 0 || f.selectedHunk < 0 || f.selectedHunk >= len(edit.Hunks) {
		return protocol.PendingEdit{}, protocol.HunkDetail{}, false
	}
	return edit, edit.Hunks[f.selectedHunk], true
}

func (f *DiffReviewFlow) dropCurrentHunk() {
	if len(f.edits) == 0 {
		return
	}
	edit := &f.edits[f.selectedEdit]
	if len(edit.Hunks) == 0 {
		return
	}
	edit.Hunks = append(edit.Hunks[:f.selectedHunk], edit.Hunks[f.selectedHunk+1:]...)
	if len(edit.Hunks) == 0 {
		f.edits = append(f.edits[:f.selectedEdit], f.edits[f.selectedEdit+1:]...)
		f.selectedEdit = clamp(f.selectedEdit, 0, max(0, len(f.edits)-1))
		f.selectedHunk = 0
	} else {
		f.selectedHunk = clamp(f.selectedHunk, 0, len(edit.Hunks)-1)
	}
	f.open = len(f.edits) > 0
	f.scroll = 0
	f.voteToastKey = ""
}

func (f *DiffReviewFlow) ApplyHunkVoteUpdate(update protocol.HunkVoteUpdate) bool {
	hunkID := normalizedVoteHunkID(update)
	if hunkID == "" {
		return false
	}
	editID := normalizedVoteEditID(update)
	for i := range f.edits {
		if editID != "" && normalizedEditID(f.edits[i]) != editID {
			continue
		}
		for j := range f.edits[i].Hunks {
			if normalizedHunkID(f.edits[i].Hunks[j]) != hunkID {
				continue
			}
			applyVoteUpdateToHunk(&f.edits[i].Hunks[j], update)
			f.voteToastKey = ""
			return true
		}
	}
	return false
}

func allEditsSafe(edits []protocol.PendingEdit) bool {
	if len(edits) == 0 {
		return false
	}
	for _, edit := range edits {
		if !editSafe(edit) {
			return false
		}
	}
	return true
}

func editSafe(edit protocol.PendingEdit) bool {
	if len(edit.Hunks) == 0 {
		return false
	}
	for _, hunk := range edit.Hunks {
		if hunk.SafetyClass != "safe" {
			return false
		}
	}
	return true
}

func normalizedEditID(edit protocol.PendingEdit) string {
	if edit.EditID != "" {
		return edit.EditID
	}
	return edit.EditIDLegacy
}

func normalizedHunkID(hunk protocol.HunkDetail) string {
	if hunk.HunkID != "" {
		return hunk.HunkID
	}
	return hunk.HunkIDLegacy
}

func editStats(edit protocol.PendingEdit) (int, int) {
	added := 0
	removed := 0
	for _, h := range edit.Hunks {
		added += h.Added
		removed += h.Removed
	}
	return added, removed
}

func (f *DiffReviewFlow) blockedByVote(want string) bool {
	_, hunk, ok := f.current()
	if !ok || !voteGate(hunk) {
		return false
	}
	return normalizeVoteStatus(hunk) != want
}

func (f *DiffReviewFlow) toastVoteBlocked() {
	_, hunk, ok := f.current()
	if !ok {
		return
	}
	key := normalizedHunkID(hunk) + ":" + normalizeVoteStatus(hunk)
	if f.voteToastKey == key {
		return
	}
	f.voteToastKey = key
	if f.state != nil {
		f.state.Dispatch(state.ActionToast{Kind: state.ToastWarning, Text: "needs vote threshold", TTL: diffVoteToastTTL})
	}
}

func voteGate(hunk protocol.HunkDetail) bool {
	threshold := normalizeVoteThreshold(hunk)
	return threshold != "" && threshold != "owner_only"
}

func normalizeVoteStatus(hunk protocol.HunkDetail) string {
	status := strings.TrimSpace(firstNonEmpty(hunk.VoteStatus, hunk.VoteStatusLegacy, hunk.VotingStatus, hunk.VotingStatusLegacy))
	if status == "" {
		status = "pending"
	}
	return strings.ToLower(status)
}

func normalizeVoteThreshold(hunk protocol.HunkDetail) string {
	return normalizeVoteValue(firstNonEmpty(hunk.VoteThreshold, hunk.VoteThresholdLegacy, hunk.Threshold))
}

func normalizeVoteValue(value string) string {
	return strings.ReplaceAll(strings.ToLower(strings.TrimSpace(value)), " ", "_")
}

func (f *DiffReviewFlow) renderVoteRow(hunk protocol.HunkDetail, width int) (string, bool) {
	threshold := normalizeVoteThreshold(hunk)
	if threshold == "" || threshold == "owner_only" {
		return "", false
	}
	row := voteRowPlain(hunk, threshold)
	return styleVoteRow(fit(row, width), f.voteTheme()), true
}

func voteRowPlain(hunk protocol.HunkDetail, threshold string) string {
	status := normalizeVoteStatus(hunk)
	approved := voteNames(hunk.Votes, "approve")
	rejected := voteNames(hunk.Votes, "reject")
	parts := []string{"votes"}
	switch status {
	case "approved":
		parts = append(parts, fmt.Sprintf("✓ %d/%d", len(approved), voteDenominator(hunk, len(approved)+len(rejected))))
	case "rejected":
		parts = append(parts, fmt.Sprintf("✗ %d/%d", len(rejected), voteDenominator(hunk, len(approved)+len(rejected))))
	default:
		if len(approved) > 0 {
			parts = append(parts, "✓ "+strings.Join(approved, ", "))
		}
		if len(rejected) > 0 {
			parts = append(parts, "✗ "+strings.Join(rejected, ", "))
		}
		if len(parts) == 1 {
			parts = append(parts, "none")
		}
	}
	suffix := status
	if threshold != "" {
		suffix += " (" + threshold + ")"
	}
	if status == "approved" || status == "rejected" {
		suffix = status
	}
	parts = append(parts, suffix)
	return "  " + strings.Join(parts, " · ")
}

func voteDenominator(hunk protocol.HunkDetail, count int) int {
	required := firstNonZero(hunk.RequiredVoters, hunk.RequiredVotersRaw)
	if required > count {
		return required
	}
	return count
}

func voteNames(votes protocol.HunkVotes, decision string) []string {
	names := make([]string, 0, len(votes))
	for _, vote := range votes {
		if normalizeVoteValue(firstNonEmpty(vote.Decision, vote.Vote)) == decision {
			names = append(names, voteDisplayName(vote))
		}
	}
	sort.Strings(names)
	return names
}

func voteDisplayName(vote protocol.HunkVote) string {
	name := strings.ReplaceAll(firstNonEmpty(vote.DisplayName, vote.DisplayNameLegacy, vote.Name, vote.ConnectionID, vote.ConnectionIDLegacy), "\n", " ")
	return strings.TrimSpace(name)
}

func styleVoteRow(row string, tm theme.Theme) string {
	out := tm.Muted.Render(row)
	out = strings.Replace(out, "✓", tm.Success.Render("✓"), 1)
	out = strings.Replace(out, "✗", tm.Error.Render("✗"), 1)
	return out
}

func (f *DiffReviewFlow) voteTheme() theme.Theme {
	if f.theme != nil {
		return *f.theme
	}
	tm := theme.DarkWithCapability(theme.CapabilityANSI16)
	return tm
}

func applyVoteUpdateToHunk(hunk *protocol.HunkDetail, update protocol.HunkVoteUpdate) {
	hunk.Votes = append(protocol.HunkVotes(nil), update.Votes...)
	if status := firstNonEmpty(update.Status, update.VoteStatus, update.VoteStatusLegacy); status != "" {
		hunk.VoteStatus = status
	}
	if threshold := firstNonEmpty(update.Threshold, update.VoteThreshold, update.VoteThresholdLegacy); threshold != "" {
		hunk.VoteThreshold = threshold
	}
	if update.RequiredVoters != 0 {
		hunk.RequiredVoters = update.RequiredVoters
	}
	if update.RequiredVotersRaw != 0 {
		hunk.RequiredVotersRaw = update.RequiredVotersRaw
	}
}

func normalizedVoteEditID(update protocol.HunkVoteUpdate) string {
	return firstNonEmpty(update.EditID, update.EditIDLegacy)
}

func normalizedVoteHunkID(update protocol.HunkVoteUpdate) string {
	return firstNonEmpty(update.HunkID, update.HunkIDLegacy)
}

func renderHunkWindow(h protocol.HunkDetail, start, limit, width int) []string {
	if limit <= 0 {
		return nil
	}
	want := limit
	total := hunkLineCount(h)
	start = clamp(start, 0, max(0, total-1))
	out := make([]string, 0, limit)
	if hunkBodyHasHeader(h) {
		for _, line := range bodyWindow(hunkBody(h), start, limit) {
			out = append(out, colorDiffLine(fit(line, width)))
		}
		for len(out) < want {
			out = append(out, fit("", width))
		}
		return out
	}
	if start == 0 {
		out = append(out, colorDiffLine(fit(nonEmpty(h.Header, "@@"), width)))
		limit--
		start++
	}
	if limit <= 0 {
		return out
	}
	bodyStart := max(0, start-1)
	for _, line := range bodyWindow(hunkBody(h), bodyStart, limit) {
		out = append(out, colorDiffLine(fit(line, width)))
	}
	for len(out) < want {
		out = append(out, fit("", width))
	}
	return out
}

func hunkLineCount(h protocol.HunkDetail) int {
	if hunkBodyHasHeader(h) {
		return lineCount(hunkBody(h))
	}
	return 1 + lineCount(hunkBody(h))
}

func hunkBodyHasHeader(h protocol.HunkDetail) bool {
	return strings.HasPrefix(strings.TrimLeft(h.Body, "\n"), "@@")
}

func hunkBody(h protocol.HunkDetail) string {
	if h.Body != "" {
		return h.Body
	}
	var b strings.Builder
	for _, line := range splitNonFinalEmpty(h.Before) {
		b.WriteByte('-')
		b.WriteString(line)
		b.WriteByte('\n')
	}
	for _, line := range splitNonFinalEmpty(h.After) {
		b.WriteByte('+')
		b.WriteString(line)
		b.WriteByte('\n')
	}
	return b.String()
}

func bodyWindow(body string, start, limit int) []string {
	if body == "" || limit <= 0 {
		return nil
	}
	out := make([]string, 0, limit)
	lineNo := 0
	lineStart := 0
	for i := 0; i <= len(body); i++ {
		if i < len(body) && body[i] != '\n' {
			continue
		}
		if i == len(body) && i == lineStart && len(body) > 0 && body[i-1] == '\n' {
			break
		}
		if lineNo >= start {
			out = append(out, body[lineStart:i])
			if len(out) == limit {
				break
			}
		}
		lineNo++
		lineStart = i + 1
	}
	return out
}

func splitNonFinalEmpty(s string) []string {
	if s == "" {
		return nil
	}
	return strings.Split(strings.TrimSuffix(s, "\n"), "\n")
}

func lineCount(s string) int {
	if s == "" {
		return 0
	}
	n := 1
	for i := 0; i < len(s); i++ {
		if s[i] == '\n' && i != len(s)-1 {
			n++
		}
	}
	return n
}

func colorDiffLine(line string) string {
	switch {
	case strings.HasPrefix(line, "@@"):
		return "\x1b[36m" + line + "\x1b[0m"
	case strings.HasPrefix(line, "+"):
		return "\x1b[32m" + line + "\x1b[0m"
	case strings.HasPrefix(line, "-"):
		return "\x1b[31m" + line + "\x1b[0m"
	default:
		return line
	}
}

func fit(line string, width int) string {
	if width <= 0 {
		return ""
	}
	for lipgloss.Width(line) > width && len([]rune(line)) > 0 {
		r := []rune(line)
		line = string(r[:len(r)-1])
	}
	return line + strings.Repeat(" ", max(0, width-lipgloss.Width(line)))
}

func nonEmpty(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}

func clamp(v, lo, hi int) int {
	if hi < lo {
		return lo
	}
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
