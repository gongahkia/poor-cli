/// Application state machine for the poor-cli TUI.
use std::collections::{HashMap, VecDeque};
use std::time::{Duration, Instant};

// ── Pair mode types ─────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PairRole {
    Driver,
    Navigator,
}

impl PairRole {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Driver => "D",
            Self::Navigator => "N",
        }
    }
    pub fn from_wire(role: &str) -> Self {
        match role {
            "prompter" => Self::Driver,
            _ => Self::Navigator,
        }
    }
}

#[derive(Debug, Clone)]
pub struct PairUser {
    pub name: String,
    pub connection_id: String,
    pub role: PairRole,
    pub is_active: bool,
}

#[derive(Debug, Clone)]
pub struct Suggestion {
    pub sender: String,
    pub text: String,
    pub received_at: Instant,
}

const SUGGESTION_TTL: Duration = Duration::from_secs(30);
const SUGGESTION_MAX: usize = 10;
pub const SUGGESTION_HINT_TTL: Duration = Duration::from_secs(15);

// ── Message model ────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum MessageRole {
    Welcome,
    User,
    Assistant,
    System,
    ToolCall { name: String },
    ToolResult { name: String },
    DiffView { name: String },
    Error,
}

#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub role: MessageRole,
    pub content: String,
    pub timestamp: Instant,
}

impl ChatMessage {
    pub fn welcome(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::Welcome,
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::User,
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::Assistant,
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::System,
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn tool_call(name: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::ToolCall { name: name.into() },
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn tool_result(name: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::ToolResult { name: name.into() },
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn diff_view(name: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::DiffView { name: name.into() },
            content: content.into(),
            timestamp: Instant::now(),
        }
    }

    pub fn error(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::Error,
            content: content.into(),
            timestamp: Instant::now(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct QueuedPrompt {
    pub display: String,
    pub backend: String,
    pub source: String,
}

impl QueuedPrompt {
    pub fn user(text: impl Into<String>) -> Self {
        let text = text.into();
        Self {
            display: text.clone(),
            backend: text,
            source: "user".to_string(),
        }
    }

    pub fn automation(display: impl Into<String>, backend: impl Into<String>) -> Self {
        Self {
            display: display.into(),
            backend: backend.into(),
            source: "automation".to_string(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ContextInspectorFile {
    pub path: String,
    pub source: String,
    pub estimated_tokens: usize,
    pub reason: String,
    pub include_full_content: bool,
    pub explicit_spec: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct ContextInspectorState {
    pub request_message: String,
    pub total_tokens: usize,
    pub budget_tokens: usize,
    pub truncated: bool,
    pub message: String,
    pub keywords: Vec<String>,
    pub files: Vec<ContextInspectorFile>,
    pub selected_index: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApprovedReviewChunk {
    pub path: String,
    pub hunk_index: usize,
}

#[derive(Debug, Clone, Default)]
pub struct MutationReviewChunk {
    pub path: String,
    pub hunk_index: usize,
    pub header: String,
    pub diff: String,
    pub selected: bool,
}

#[derive(Debug, Clone, Default)]
pub struct MutationReviewState {
    pub request_id: String,
    pub tool_name: String,
    pub operation: String,
    pub prompt_id: String,
    pub paths: Vec<String>,
    pub diff: String,
    pub checkpoint_id: Option<String>,
    pub changed: Option<bool>,
    pub message: String,
    pub selected_path_index: usize,
    pub chunks: Vec<MutationReviewChunk>,
    pub selected_chunk_index: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MutationReviewFileGroup {
    pub path: String,
    pub chunk_indexes: Vec<usize>,
    pub selected_chunks: usize,
}

impl MutationReviewFileGroup {
    pub fn total_chunks(&self) -> usize {
        self.chunk_indexes.len()
    }

    pub fn decision_state(&self) -> ReviewDecisionState {
        if self.selected_chunks == 0 {
            ReviewDecisionState::Rejected
        } else if self.selected_chunks == self.total_chunks() {
            ReviewDecisionState::Accepted
        } else {
            ReviewDecisionState::Partial
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReviewDecisionState {
    Accepted,
    Partial,
    Rejected,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewDecisionFileSummary {
    pub path: String,
    pub state: ReviewDecisionState,
    pub total_hunks: usize,
    pub accepted_hunks: Vec<usize>,
    pub rejected_hunks: Vec<usize>,
}

impl ReviewDecisionFileSummary {
    pub fn summary_line(&self) -> String {
        match self.total_hunks {
            0 => match self.state {
                ReviewDecisionState::Accepted => format!("{}: accepted", self.path),
                ReviewDecisionState::Partial => format!("{}: partial", self.path),
                ReviewDecisionState::Rejected => format!("{}: rejected", self.path),
            },
            _ => {
                let accepted = format_hunk_labels(&self.accepted_hunks);
                let rejected = format_hunk_labels(&self.rejected_hunks);
                match self.state {
                    ReviewDecisionState::Accepted => {
                        format!("{}: accepted hunks {}", self.path, accepted)
                    }
                    ReviewDecisionState::Rejected => {
                        format!("{}: rejected hunks {}", self.path, rejected)
                    }
                    ReviewDecisionState::Partial => format!(
                        "{}: accepted {}; rejected {}",
                        self.path, accepted, rejected
                    ),
                }
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewDecisionSummary {
    pub total_files: usize,
    pub accepted_files: usize,
    pub total_hunks: usize,
    pub accepted_hunks: usize,
    pub files: Vec<ReviewDecisionFileSummary>,
}

impl ReviewDecisionSummary {
    pub fn headline(&self) -> String {
        if self.total_hunks > 0 {
            if self.accepted_hunks == 0 {
                format!(
                    "Rejected all {} hunks across {} files",
                    self.total_hunks, self.total_files
                )
            } else if self.accepted_hunks == self.total_hunks {
                format!(
                    "Accepted all {} hunks across {} files",
                    self.total_hunks, self.total_files
                )
            } else {
                format!(
                    "Accepted {}/{} hunks across {}/{} files",
                    self.accepted_hunks, self.total_hunks, self.accepted_files, self.total_files
                )
            }
        } else if self.accepted_files == 0 {
            format!("Rejected all {} files", self.total_files)
        } else if self.accepted_files == self.total_files {
            format!("Accepted all {} files", self.total_files)
        } else {
            format!(
                "Accepted {}/{} files",
                self.accepted_files, self.total_files
            )
        }
    }
}

impl MutationReviewState {
    pub fn supports_chunk_approval(&self) -> bool {
        self.tool_name == "apply_patch_unified" && !self.chunks.is_empty()
    }

    pub fn selected_chunk(&self) -> Option<&MutationReviewChunk> {
        self.chunks.get(self.selected_chunk_index)
    }

    pub fn sync_selected_path_from_chunk(&mut self) {
        if let Some(chunk) = self.selected_chunk() {
            if let Some(index) = self.paths.iter().position(|path| path == &chunk.path) {
                self.selected_path_index = index;
            }
        }
    }

    pub fn approved_chunks(&self) -> Vec<ApprovedReviewChunk> {
        self.chunks
            .iter()
            .filter(|chunk| chunk.selected)
            .map(|chunk| ApprovedReviewChunk {
                path: chunk.path.clone(),
                hunk_index: chunk.hunk_index,
            })
            .collect()
    }

    pub fn file_groups(&self) -> Vec<MutationReviewFileGroup> {
        let mut groups: Vec<MutationReviewFileGroup> = Vec::new();
        let mut positions: HashMap<&str, usize> = HashMap::new();

        for (index, chunk) in self.chunks.iter().enumerate() {
            if let Some(position) = positions.get(chunk.path.as_str()).copied() {
                let group = &mut groups[position];
                group.chunk_indexes.push(index);
                if chunk.selected {
                    group.selected_chunks += 1;
                }
            } else {
                positions.insert(chunk.path.as_str(), groups.len());
                groups.push(MutationReviewFileGroup {
                    path: chunk.path.clone(),
                    chunk_indexes: vec![index],
                    selected_chunks: usize::from(chunk.selected),
                });
            }
        }

        groups
    }

    pub fn selected_file_group_index(&self) -> Option<usize> {
        let groups = self.file_groups();
        groups.iter().enumerate().find_map(|(group_index, group)| {
            group
                .chunk_indexes
                .contains(&self.selected_chunk_index)
                .then_some(group_index)
        })
    }

    pub fn jump_to_file_group(&mut self, reverse: bool) -> bool {
        let groups = self.file_groups();
        if groups.is_empty() {
            return false;
        }

        let current = self.selected_file_group_index().unwrap_or(0);
        let target = if reverse {
            current.saturating_sub(1)
        } else if current + 1 < groups.len() {
            current + 1
        } else {
            current
        };

        if target == current {
            return false;
        }

        if let Some(next_chunk_index) = groups[target].chunk_indexes.first().copied() {
            self.selected_chunk_index = next_chunk_index;
            self.sync_selected_path_from_chunk();
            return true;
        }

        false
    }

    pub fn set_current_file_group_selection(&mut self, selected: bool) -> Option<String> {
        let groups = self.file_groups();
        let group_index = self.selected_file_group_index()?;
        let group = groups.get(group_index)?;
        for chunk_index in &group.chunk_indexes {
            if let Some(chunk) = self.chunks.get_mut(*chunk_index) {
                chunk.selected = selected;
            }
        }
        Some(group.path.clone())
    }

    pub fn build_decision_summary(
        &self,
        allowed: bool,
        approved_paths: &[String],
        approved_chunks: &[ApprovedReviewChunk],
    ) -> ReviewDecisionSummary {
        if self.supports_chunk_approval() {
            return self.build_chunk_decision_summary(allowed, approved_paths, approved_chunks);
        }

        self.build_path_decision_summary(allowed, approved_paths)
    }

    fn build_chunk_decision_summary(
        &self,
        allowed: bool,
        approved_paths: &[String],
        approved_chunks: &[ApprovedReviewChunk],
    ) -> ReviewDecisionSummary {
        let accepted_keys = if !allowed {
            std::collections::HashSet::new()
        } else if !approved_chunks.is_empty() {
            approved_chunks
                .iter()
                .map(|chunk| (chunk.path.clone(), chunk.hunk_index))
                .collect::<std::collections::HashSet<_>>()
        } else if !approved_paths.is_empty() {
            self.chunks
                .iter()
                .filter(|chunk| approved_paths.iter().any(|path| path == &chunk.path))
                .map(|chunk| (chunk.path.clone(), chunk.hunk_index))
                .collect::<std::collections::HashSet<_>>()
        } else {
            self.chunks
                .iter()
                .map(|chunk| (chunk.path.clone(), chunk.hunk_index))
                .collect::<std::collections::HashSet<_>>()
        };

        let groups = self.file_groups();
        let files = groups
            .into_iter()
            .map(|group| {
                let mut accepted_hunks = Vec::new();
                let mut rejected_hunks = Vec::new();

                for chunk_index in group.chunk_indexes {
                    if let Some(chunk) = self.chunks.get(chunk_index) {
                        if accepted_keys.contains(&(chunk.path.clone(), chunk.hunk_index)) {
                            accepted_hunks.push(chunk.hunk_index);
                        } else {
                            rejected_hunks.push(chunk.hunk_index);
                        }
                    }
                }

                let state = if accepted_hunks.is_empty() {
                    ReviewDecisionState::Rejected
                } else if rejected_hunks.is_empty() {
                    ReviewDecisionState::Accepted
                } else {
                    ReviewDecisionState::Partial
                };

                ReviewDecisionFileSummary {
                    path: group.path,
                    state,
                    total_hunks: accepted_hunks.len() + rejected_hunks.len(),
                    accepted_hunks,
                    rejected_hunks,
                }
            })
            .collect::<Vec<_>>();

        ReviewDecisionSummary {
            total_files: files.len(),
            accepted_files: files
                .iter()
                .filter(|file| file.state != ReviewDecisionState::Rejected)
                .count(),
            total_hunks: files.iter().map(|file| file.total_hunks).sum(),
            accepted_hunks: files.iter().map(|file| file.accepted_hunks.len()).sum(),
            files,
        }
    }

    fn build_path_decision_summary(
        &self,
        allowed: bool,
        approved_paths: &[String],
    ) -> ReviewDecisionSummary {
        let paths = if self.paths.is_empty() {
            vec![self.tool_name.clone()]
        } else {
            self.paths.clone()
        };

        let files = paths
            .into_iter()
            .map(|path| {
                let accepted = allowed
                    && (approved_paths.is_empty()
                        || approved_paths.iter().any(|item| item == &path));
                ReviewDecisionFileSummary {
                    path,
                    state: if accepted {
                        ReviewDecisionState::Accepted
                    } else {
                        ReviewDecisionState::Rejected
                    },
                    total_hunks: 0,
                    accepted_hunks: Vec::new(),
                    rejected_hunks: Vec::new(),
                }
            })
            .collect::<Vec<_>>();

        ReviewDecisionSummary {
            total_files: files.len(),
            accepted_files: files
                .iter()
                .filter(|file| file.state == ReviewDecisionState::Accepted)
                .count(),
            total_hunks: 0,
            accepted_hunks: 0,
            files,
        }
    }
}

#[derive(Debug, Clone)]
pub enum TimelineEntryKind {
    Phase,
    ToolCall,
    ToolResult,
    Permission,
    Diff,
    Cost,
    Note,
}

#[derive(Debug, Clone)]
pub struct TimelineEntry {
    pub kind: TimelineEntryKind,
    pub request_id: String,
    pub title: String,
    pub detail: String,
    pub diff: String,
    pub paths: Vec<String>,
    pub checkpoint_id: Option<String>,
    pub changed: Option<bool>,
    pub review_summary: Option<ReviewDecisionSummary>,
    pub timestamp: Instant,
}

#[derive(Debug, Clone)]
pub enum QuickOpenItemKind {
    Command,
    File,
    Checkpoint,
    Prompt,
}

#[derive(Debug, Clone)]
pub struct QuickOpenItem {
    pub kind: QuickOpenItemKind,
    pub label: String,
    pub detail: String,
    pub value: String,
}

#[derive(Debug, Clone, Default)]
pub struct QuickOpenState {
    pub query: String,
    pub selected_index: usize,
    pub items: Vec<QuickOpenItem>,
}

#[derive(Debug, Clone, Default)]
pub struct ResumeDashboardState {
    pub last_session_summary: String,
    pub recent_checkpoints: Vec<String>,
    pub recent_edits: Vec<String>,
    pub active_services: Vec<String>,
    pub git_summary: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TranscriptSearchItemKind {
    Message,
    Tool,
    Diff,
}

#[derive(Debug, Clone)]
pub struct TranscriptSearchItem {
    pub kind: TranscriptSearchItemKind,
    pub label: String,
    pub detail: String,
    pub paths: Vec<String>,
    pub diff: String,
    pub timestamp: Instant,
}

#[derive(Debug, Clone)]
pub struct TranscriptSearchState {
    pub query: String,
    pub selected_index: usize,
    pub include_messages: bool,
    pub include_tools: bool,
    pub include_diffs: bool,
}

impl Default for TranscriptSearchState {
    fn default() -> Self {
        Self {
            query: String::new(),
            selected_index: 0,
            include_messages: true,
            include_tools: true,
            include_diffs: true,
        }
    }
}

fn normalize_review_chunk_path(raw_path: &str, fallback_paths: &[String]) -> String {
    let trimmed = raw_path
        .trim()
        .trim_start_matches("a/")
        .trim_start_matches("b/");
    if trimmed.is_empty() || trimmed == "/dev/null" {
        return fallback_paths.first().cloned().unwrap_or_default();
    }
    if trimmed.starts_with('/') {
        return trimmed.to_string();
    }

    let mut matches = fallback_paths
        .iter()
        .filter(|path| path.ends_with(trimmed))
        .cloned()
        .collect::<Vec<_>>();
    if matches.len() == 1 {
        return matches.remove(0);
    }

    let file_name = trimmed.rsplit('/').next().unwrap_or(trimmed);
    matches = fallback_paths
        .iter()
        .filter(|path| path.rsplit('/').next().unwrap_or("") == file_name)
        .cloned()
        .collect::<Vec<_>>();
    if matches.len() == 1 {
        return matches.remove(0);
    }

    trimmed.to_string()
}

fn format_hunk_labels(hunks: &[usize]) -> String {
    if hunks.is_empty() {
        return "none".to_string();
    }

    hunks
        .iter()
        .map(|index| format!("h{}", index + 1))
        .collect::<Vec<_>>()
        .join(", ")
}

fn parse_mutation_review_chunks(diff: &str, fallback_paths: &[String]) -> Vec<MutationReviewChunk> {
    let mut chunks: Vec<MutationReviewChunk> = Vec::new();
    let mut current_path = fallback_paths.first().cloned().unwrap_or_default();
    let mut current_lines: Vec<String> = Vec::new();
    let mut current_header = String::new();
    let mut hunk_indexes: std::collections::HashMap<String, usize> =
        std::collections::HashMap::new();

    for line in diff.lines() {
        if line.starts_with("diff --git ") || line.starts_with("--- ") {
            if !current_lines.is_empty() {
                let chunk_path = if current_path.is_empty() {
                    fallback_paths.first().cloned().unwrap_or_default()
                } else {
                    current_path.clone()
                };
                let next_index = hunk_indexes.entry(chunk_path.clone()).or_insert(0usize);
                chunks.push(MutationReviewChunk {
                    path: chunk_path,
                    hunk_index: *next_index,
                    header: current_header.clone(),
                    diff: current_lines.join("\n"),
                    selected: false,
                });
                *next_index += 1;
                current_lines.clear();
            }
            if line.starts_with("--- ") {
                continue;
            }
        }
        if let Some(raw_path) = line.strip_prefix("+++ ") {
            current_path = normalize_review_chunk_path(raw_path, fallback_paths);
            continue;
        }

        if line.starts_with("@@") {
            if !current_lines.is_empty() {
                let chunk_path = if current_path.is_empty() {
                    fallback_paths.first().cloned().unwrap_or_default()
                } else {
                    current_path.clone()
                };
                let next_index = hunk_indexes.entry(chunk_path.clone()).or_insert(0usize);
                chunks.push(MutationReviewChunk {
                    path: chunk_path,
                    hunk_index: *next_index,
                    header: current_header.clone(),
                    diff: current_lines.join("\n"),
                    selected: false,
                });
                *next_index += 1;
                current_lines.clear();
            }
            current_header = line.to_string();
            current_lines.push(line.to_string());
            continue;
        }

        if !current_lines.is_empty() {
            current_lines.push(line.to_string());
        }
    }

    if !current_lines.is_empty() {
        let chunk_path = if current_path.is_empty() {
            fallback_paths.first().cloned().unwrap_or_default()
        } else {
            current_path
        };
        let next_index = hunk_indexes.entry(chunk_path.clone()).or_insert(0usize);
        chunks.push(MutationReviewChunk {
            path: chunk_path,
            hunk_index: *next_index,
            header: current_header,
            diff: current_lines.join("\n"),
            selected: false,
        });
    }

    if chunks.is_empty() && !diff.trim().is_empty() {
        chunks.push(MutationReviewChunk {
            path: fallback_paths.first().cloned().unwrap_or_default(),
            hunk_index: 0,
            header: "Full diff".to_string(),
            diff: diff.to_string(),
            selected: false,
        });
    }

    chunks
}

// ── Application state ────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum AppMode {
    Normal,
    Command,
    ProviderSelect,
    InfoPopup,
    PermissionPrompt,
    MutationReview,
    ContextInspector,
    QuickOpen,
    Timeline,
    TranscriptSearch,
    PlanReview,
    CompactSelect,
    JoinWizard,
    Quitting,
}

#[derive(Debug, Clone)]
pub struct PlanStep {
    pub description: String,
    pub status: PlanStepStatus,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PlanStepStatus {
    Pending,
    Running,
    Done,
    Skipped,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResponseMode {
    Poor,
    Rich,
}

impl ResponseMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Poor => "poor",
            Self::Rich => "rich",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThemeMode {
    Dark,
    Light,
}

impl ThemeMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Dark => "dark",
            Self::Light => "light",
        }
    }

    pub fn from_ui_theme(value: &str) -> Self {
        match value.trim().to_lowercase().as_str() {
            "light" => Self::Light,
            "dark" | "default" | "minimal" | "" => Self::Dark,
            _ => Self::Dark,
        }
    }

    pub fn from_user_input(value: &str) -> Option<Self> {
        match value.trim().to_lowercase().as_str() {
            "dark" => Some(Self::Dark),
            "light" => Some(Self::Light),
            _ => None,
        }
    }
}

/// Spinner frames for the thinking indicator.
pub const SPINNER_FRAMES: &[&str] = &["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

pub const COMPACT_STRATEGIES: &[(&str, &str)] = &[
    ("compact", "Summarize conversation in-place"),
    ("compress", "Strip tool calls, keep text only"),
    ("handoff", "New session with context summary"),
];

pub const THINKING_FRAMES: &[&str] = &[
    "▁▂▃▂",
    "▂▃▄▃",
    "▃▄▅▄",
    "▄▅▆▅",
    "▅▆▇▆",
    "▆▇█▇",
    "▅▆▇▆",
    "▄▅▆▅",
];

#[derive(Debug, Clone)]
pub struct ProviderEntry {
    pub name: String,
    pub available: bool,
    pub models: Vec<String>,
}

pub struct App {
    // ── Chat state ───
    pub messages: Vec<ChatMessage>,
    pub input_buffer: String,
    pub input_cursor: usize,

    // ── Scroll ───
    pub scroll_offset: u16,

    // ── Mode ───
    pub mode: AppMode,

    // ── Provider info ───
    pub provider_name: String,
    pub model_name: String,
    pub capabilities: Vec<String>,
    pub providers: Vec<ProviderEntry>,
    pub provider_select_idx: usize,
    pub info_popup_title: String,
    pub info_popup_content: String,
    pub info_popup_scroll: u16,

    // ── Session info ───
    pub streaming_enabled: bool,
    pub version: String,

    // ── Waiting / spinner ───
    pub waiting: bool,
    pub spinner_tick: usize,
    pub wait_start: Option<Instant>,

    // ── Prompt queue (steering harness) ───
    pub prompt_queue: VecDeque<QueuedPrompt>,

    // ── Command history ───
    pub command_history: VecDeque<String>,
    pub history_index: Option<usize>,
    pub command_match_index: usize,

    // ── Permission prompt state ───
    pub permission_message: String,
    pub permission_answer: Option<bool>,
    pub permission_prompt_id: String,
    pub permission_approved_paths: Vec<String>,
    pub permission_approved_chunks: Vec<ApprovedReviewChunk>,
    pub mutation_review: Option<MutationReviewState>,
    pub context_inspector: Option<ContextInspectorState>,
    pub quick_open: QuickOpenState,
    pub timeline_entries: Vec<TimelineEntry>,
    pub timeline_scroll: u16,
    pub transcript_search: TranscriptSearchState,
    pub permission_mode_label: String,

    // ── Status message (temporary) ───
    pub status_message: Option<(String, Instant)>,

    // ── Whether server is connected ───
    pub server_connected: bool,

    // ── Working directory ───
    pub cwd: String,

    // ── Local provider flag (ollama) ───
    pub is_local_provider: bool,

    // ── Session metrics ───
    pub session_started_at: Instant,
    pub session_requests: usize,
    pub input_chars: usize,
    pub output_chars: usize,
    pub input_tokens_estimate: usize,
    pub output_tokens_estimate: usize,
    pub last_user_message: Option<String>,
    pub pending_images: Vec<String>,
    pub pinned_context_files: Vec<String>,
    pub pending_prompt_save_name: Option<String>,
    pub onboarding_active: bool,
    pub onboarding_step: usize,
    pub join_wizard_active: bool,
    pub join_wizard_step: u8,
    pub join_wizard_url: String,
    pub join_wizard_room: String,
    pub join_wizard_input: String,
    pub join_wizard_error: String,
    pub autopilot_enabled: bool,
    pub last_command_output: Option<String>,
    pub execution_profile: String,
    pub context_budget_tokens: usize,
    pub context_budget_files: Vec<String>,
    pub context_budget_estimated_tokens: usize,
    pub last_mutation_checkpoint_id: Option<String>,
    pub last_mutation_diff: String,
    pub recent_edited_files: VecDeque<String>,
    pub recent_prompts: VecDeque<String>,
    pub recent_checkpoints: VecDeque<String>,
    pub git_branch: String,
    pub git_dirty: bool,
    pub resume_dashboard: ResumeDashboardState,
    pub qa_mode_enabled: bool,
    pub qa_command: String,
    pub multiplayer_enabled: bool,
    pub multiplayer_room: String,
    pub multiplayer_role: String,
    pub multiplayer_remote_url: String,
    pub multiplayer_remote_token: String,
    pub multiplayer_queue_depth: u64,
    pub multiplayer_member_count: u64,
    pub multiplayer_active_connection_id: String,
    pub multiplayer_lobby_enabled: bool,
    pub multiplayer_preset: String,
    pub multiplayer_member_roles: Vec<String>,

    // ── Streaming / agentic state ───
    pub streaming_message: Option<usize>, // index of in-progress assistant message
    pub current_iteration: u32,
    pub iteration_cap: u32,
    pub active_tool: Option<String>,
    pub request_id_counter: u64,
    pub active_request_id: String,
    pub active_request_started_at: Option<Instant>,

    // ── Plan mode state ───
    pub plan_steps: Vec<PlanStep>,
    pub plan_current_step: usize,
    pub plan_original_request: String,
    pub plan_summary: String,
    pub plan_prompt_id: String,
    pub plan_is_execution_gate: bool,

    // ── Real token tracking (from server) ───
    pub turn_input_tokens: u64,
    pub turn_output_tokens: u64,
    pub cumulative_input_tokens: u64,
    pub cumulative_output_tokens: u64,
    pub response_mode: ResponseMode,
    pub theme_mode: ThemeMode,
    pub compact_select_idx: usize,

    // ── Reconnect message tracking ───
    pub reconnect_message_idx: Option<usize>,

    // ── Pair mode state ───
    pub pair_mode_active: bool,
    pub pair_short_code: String,
    pub pair_invite_code: String,
    pub pair_is_host: bool,
    pub connected_users: Vec<PairUser>,
    pub suggestions: VecDeque<Suggestion>,
}

impl Default for App {
    fn default() -> Self {
        Self {
            messages: Vec::new(),
            input_buffer: String::new(),
            input_cursor: 0,
            scroll_offset: 0,
            mode: AppMode::Normal,
            provider_name: "unknown".into(),
            model_name: "unknown".into(),
            capabilities: Vec::new(),
            providers: Vec::new(),
            provider_select_idx: 0,
            info_popup_title: String::new(),
            info_popup_content: String::new(),
            info_popup_scroll: 0,
            streaming_enabled: true,
            version: "0.4.0".into(),
            waiting: false,
            spinner_tick: 0,
            wait_start: None,
            prompt_queue: VecDeque::new(),
            command_history: VecDeque::with_capacity(100),
            history_index: None,
            command_match_index: 0,
            permission_message: String::new(),
            permission_answer: None,
            permission_prompt_id: String::new(),
            permission_approved_paths: Vec::new(),
            permission_approved_chunks: Vec::new(),
            mutation_review: None,
            context_inspector: None,
            quick_open: QuickOpenState::default(),
            timeline_entries: Vec::new(),
            timeline_scroll: 0,
            transcript_search: TranscriptSearchState::default(),
            permission_mode_label: "prompt".to_string(),
            status_message: None,
            server_connected: false,
            cwd: String::new(),
            is_local_provider: false,
            session_started_at: Instant::now(),
            session_requests: 0,
            input_chars: 0,
            output_chars: 0,
            input_tokens_estimate: 0,
            output_tokens_estimate: 0,
            last_user_message: None,
            pending_images: Vec::new(),
            pinned_context_files: Vec::new(),
            pending_prompt_save_name: None,
            onboarding_active: false,
            onboarding_step: 0,
            join_wizard_active: false,
            join_wizard_step: 0,
            join_wizard_url: String::new(),
            join_wizard_room: String::new(),
            join_wizard_input: String::new(),
            join_wizard_error: String::new(),
            autopilot_enabled: false,
            last_command_output: None,
            execution_profile: "safe".to_string(),
            context_budget_tokens: 6000,
            context_budget_files: Vec::new(),
            context_budget_estimated_tokens: 0,
            last_mutation_checkpoint_id: None,
            last_mutation_diff: String::new(),
            recent_edited_files: VecDeque::new(),
            recent_prompts: VecDeque::new(),
            recent_checkpoints: VecDeque::new(),
            git_branch: String::new(),
            git_dirty: false,
            resume_dashboard: ResumeDashboardState::default(),
            qa_mode_enabled: false,
            qa_command: String::new(),
            multiplayer_enabled: false,
            multiplayer_room: String::new(),
            multiplayer_role: String::new(),
            multiplayer_remote_url: String::new(),
            multiplayer_remote_token: String::new(),
            multiplayer_queue_depth: 0,
            multiplayer_member_count: 0,
            multiplayer_active_connection_id: String::new(),
            multiplayer_lobby_enabled: false,
            multiplayer_preset: String::new(),
            multiplayer_member_roles: Vec::new(),
            streaming_message: None,
            current_iteration: 0,
            iteration_cap: 25,
            active_tool: None,
            request_id_counter: 0,
            active_request_id: String::new(),
            active_request_started_at: None,
            plan_steps: Vec::new(),
            plan_current_step: 0,
            plan_original_request: String::new(),
            plan_summary: String::new(),
            plan_prompt_id: String::new(),
            plan_is_execution_gate: false,
            turn_input_tokens: 0,
            turn_output_tokens: 0,
            cumulative_input_tokens: 0,
            cumulative_output_tokens: 0,
            response_mode: ResponseMode::Rich,
            theme_mode: ThemeMode::Dark,
            compact_select_idx: 0,
            reconnect_message_idx: None,
            pair_mode_active: false,
            pair_short_code: String::new(),
            pair_invite_code: String::new(),
            pair_is_host: false,
            connected_users: Vec::new(),
            suggestions: VecDeque::new(),
        }
    }
}

impl App {
    pub fn new() -> Self {
        Self::default()
    }

    fn welcome_text(&self) -> String {
        let workspace = if self.cwd.trim().is_empty() {
            "(workspace unavailable)".to_string()
        } else {
            self.cwd.clone()
        };
        let model_display = if self.model_name.trim().is_empty() || self.model_name == "unknown" {
            self.provider_name.clone()
        } else {
            self.model_name.clone()
        };
        let last_session_line = if self.resume_dashboard.last_session_summary.is_empty() {
            String::new()
        } else {
            format!(
                "\nlast session  {}",
                self.resume_dashboard.last_session_summary
            )
        };
        format!(
            ">_ poor-cli (v{version})\n\
            \n\
            model:     {model_display}   /switch to change\n\
            directory: {workspace}\n\n\
            ? for shortcuts{last_session_line}",
            version = self.version,
            model_display = model_display,
            workspace = workspace,
            last_session_line = last_session_line,
        )
    }

    /// Add a welcome message on startup.
    pub fn add_welcome(&mut self) {
        self.messages
            .push(ChatMessage::welcome(self.welcome_text()));
        self.scroll_offset = 0;
    }

    /// Retroactively update the welcome message after init completes.
    pub fn update_welcome(&mut self) {
        let text = self.welcome_text();
        if let Some(msg) = self.messages.first_mut() {
            if matches!(msg.role, MessageRole::Welcome) {
                msg.content = text;
            }
        }
        self.scroll_offset = 0;
    }

    /// Push a message and auto-scroll to bottom.
    pub fn push_message(&mut self, msg: ChatMessage) {
        self.messages.push(msg);
        // Reset scroll to bottom
        self.scroll_offset = 0;
    }

    /// Start waiting for a response.
    pub fn start_waiting(&mut self) {
        self.waiting = true;
        self.spinner_tick = 0;
        self.wait_start = Some(Instant::now());
    }

    /// Stop waiting.
    pub fn stop_waiting(&mut self) {
        self.waiting = false;
        self.wait_start = None;
    }

    /// Advance the spinner.
    pub fn tick_spinner(&mut self) {
        if self.waiting {
            self.spinner_tick = (self.spinner_tick + 1) % SPINNER_FRAMES.len();
        }
    }

    /// Get the current spinner frame.
    pub fn spinner_frame(&self) -> &str {
        SPINNER_FRAMES[self.spinner_tick % SPINNER_FRAMES.len()]
    }

    pub fn thinking_frame(&self) -> &str {
        THINKING_FRAMES[self.spinner_tick % THINKING_FRAMES.len()]
    }

    /// Get elapsed wait time string.
    pub fn wait_elapsed(&self) -> String {
        if let Some(start) = self.wait_start {
            let secs = start.elapsed().as_secs_f64();
            format!("{secs:.1}s")
        } else {
            String::new()
        }
    }

    /// Insert a character at the cursor.
    pub fn insert_char(&mut self, c: char) {
        self.input_buffer.insert(self.input_cursor, c);
        self.input_cursor += c.len_utf8();
        self.history_index = None;
    }

    /// Delete the character before the cursor.
    pub fn backspace(&mut self) {
        if self.input_cursor > 0 {
            // Find the previous char boundary
            let prev = self.input_buffer[..self.input_cursor]
                .char_indices()
                .last()
                .map(|(idx, _)| idx)
                .unwrap_or(0);
            self.input_buffer.drain(prev..self.input_cursor);
            self.input_cursor = prev;
        }
    }

    /// Delete the character at the cursor.
    pub fn delete_char(&mut self) {
        if self.input_cursor < self.input_buffer.len() {
            let next = self.input_buffer[self.input_cursor..]
                .char_indices()
                .nth(1)
                .map(|(idx, _)| self.input_cursor + idx)
                .unwrap_or(self.input_buffer.len());
            self.input_buffer.drain(self.input_cursor..next);
        }
    }

    /// Move cursor left.
    pub fn cursor_left(&mut self) {
        if self.input_cursor > 0 {
            self.input_cursor = self.input_buffer[..self.input_cursor]
                .char_indices()
                .last()
                .map(|(idx, _)| idx)
                .unwrap_or(0);
        }
    }

    /// Move cursor right.
    pub fn cursor_right(&mut self) {
        if self.input_cursor < self.input_buffer.len() {
            self.input_cursor = self.input_buffer[self.input_cursor..]
                .char_indices()
                .nth(1)
                .map(|(idx, _)| self.input_cursor + idx)
                .unwrap_or(self.input_buffer.len());
        }
    }

    /// Move cursor to start.
    pub fn cursor_home(&mut self) {
        self.input_cursor = 0;
    }

    /// Move cursor to end.
    pub fn cursor_end(&mut self) {
        self.input_cursor = self.input_buffer.len();
    }

    /// Take the input buffer content and reset it.
    pub fn take_input(&mut self) -> String {
        let text = self.input_buffer.clone();
        self.input_buffer.clear();
        self.input_cursor = 0;
        self.history_index = None;
        self.command_match_index = 0;

        // Save to history (redact sensitive command arguments).
        let history_entry = redact_sensitive_history_command(&text);
        if !history_entry.is_empty() {
            self.command_history.push_front(history_entry);
            if self.command_history.len() > 100 {
                self.command_history.pop_back();
            }
        }
        text
    }

    /// Navigate to the previous history entry.
    pub fn history_prev(&mut self) {
        if self.command_history.is_empty() {
            return;
        }
        self.command_match_index = 0;
        let idx = match self.history_index {
            None => 0,
            Some(i) => (i + 1).min(self.command_history.len() - 1),
        };
        self.history_index = Some(idx);
        if let Some(entry) = self.command_history.get(idx) {
            self.input_buffer = entry.clone();
            self.input_cursor = self.input_buffer.len();
        }
    }

    /// Navigate to the next history entry.
    pub fn history_next(&mut self) {
        self.command_match_index = 0;
        match self.history_index {
            None => {}
            Some(0) => {
                self.history_index = None;
                self.input_buffer.clear();
                self.input_cursor = 0;
            }
            Some(i) => {
                let idx = i - 1;
                self.history_index = Some(idx);
                if let Some(entry) = self.command_history.get(idx) {
                    self.input_buffer = entry.clone();
                    self.input_cursor = self.input_buffer.len();
                }
            }
        }
    }

    /// Scroll up in the message history.
    pub fn scroll_up(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_add(amount);
    }

    /// Scroll down in the message history.
    pub fn scroll_down(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_sub(amount);
    }

    /// Set a temporary status message.
    pub fn set_status(&mut self, msg: impl Into<String>) {
        self.status_message = Some((msg.into(), Instant::now()));
    }

    pub fn push_timeline_entry(&mut self, entry: TimelineEntry) {
        self.timeline_entries.push(entry);
        if self.timeline_entries.len() > 200 {
            let overflow = self.timeline_entries.len() - 200;
            self.timeline_entries.drain(0..overflow);
        }
        self.timeline_scroll = 0;
    }

    pub fn open_context_inspector(&mut self, state: ContextInspectorState) {
        self.context_inspector = Some(state);
        self.mode = AppMode::ContextInspector;
    }

    pub fn close_context_inspector(&mut self) {
        self.context_inspector = None;
        self.mode = AppMode::Normal;
    }

    pub fn open_mutation_review(&mut self, mut state: MutationReviewState) {
        if state.chunks.is_empty() {
            state.chunks = parse_mutation_review_chunks(&state.diff, &state.paths);
        }
        state.sync_selected_path_from_chunk();
        self.permission_prompt_id = state.prompt_id.clone();
        self.permission_approved_paths.clear();
        self.permission_approved_chunks.clear();
        self.permission_message = if state.message.is_empty() {
            state.tool_name.clone()
        } else {
            state.message.clone()
        };
        self.mutation_review = Some(state);
        self.mode = AppMode::MutationReview;
    }

    pub fn close_mutation_review(&mut self) {
        self.mutation_review = None;
        self.permission_approved_paths.clear();
        self.permission_approved_chunks.clear();
        self.mode = AppMode::Normal;
    }

    pub fn open_quick_open(&mut self, items: Vec<QuickOpenItem>) {
        self.quick_open = QuickOpenState {
            query: String::new(),
            selected_index: 0,
            items,
        };
        self.mode = AppMode::QuickOpen;
    }

    pub fn close_quick_open(&mut self) {
        self.quick_open = QuickOpenState::default();
        self.mode = AppMode::Normal;
    }

    pub fn open_timeline(&mut self) {
        self.mode = AppMode::Timeline;
    }

    pub fn close_timeline(&mut self) {
        self.mode = AppMode::Normal;
    }

    pub fn open_transcript_search(&mut self) {
        self.transcript_search = TranscriptSearchState::default();
        self.mode = AppMode::TranscriptSearch;
    }

    pub fn close_transcript_search(&mut self) {
        self.transcript_search = TranscriptSearchState::default();
        self.mode = AppMode::Normal;
    }

    pub fn transcript_search_items(&self) -> Vec<TranscriptSearchItem> {
        let mut items: Vec<TranscriptSearchItem> = Vec::new();
        let query = self.transcript_search.query.trim().to_lowercase();

        for message in &self.messages {
            let (kind, label) = match &message.role {
                MessageRole::Welcome => (TranscriptSearchItemKind::Message, "Welcome".to_string()),
                MessageRole::User => (TranscriptSearchItemKind::Message, "User".to_string()),
                MessageRole::Assistant => {
                    (TranscriptSearchItemKind::Message, "Assistant".to_string())
                }
                MessageRole::System => (TranscriptSearchItemKind::Message, "System".to_string()),
                MessageRole::Error => (TranscriptSearchItemKind::Message, "Error".to_string()),
                MessageRole::ToolCall { name } => (
                    TranscriptSearchItemKind::Tool,
                    format!("Tool call / {name}"),
                ),
                MessageRole::ToolResult { name } => (
                    TranscriptSearchItemKind::Tool,
                    format!("Tool result / {name}"),
                ),
                MessageRole::DiffView { name } => {
                    (TranscriptSearchItemKind::Diff, format!("Diff / {name}"))
                }
            };

            if kind == TranscriptSearchItemKind::Message && !self.transcript_search.include_messages
            {
                continue;
            }
            if kind == TranscriptSearchItemKind::Tool && !self.transcript_search.include_tools {
                continue;
            }
            if kind == TranscriptSearchItemKind::Diff && !self.transcript_search.include_diffs {
                continue;
            }

            items.push(TranscriptSearchItem {
                kind,
                label,
                detail: message.content.clone(),
                paths: Vec::new(),
                diff: if matches!(&message.role, MessageRole::DiffView { .. }) {
                    message.content.clone()
                } else {
                    String::new()
                },
                timestamp: message.timestamp,
            });
        }

        for entry in &self.timeline_entries {
            let (kind, label, diff) = if (!entry.diff.is_empty()
                || matches!(entry.kind, TimelineEntryKind::Diff))
                && self.transcript_search.include_diffs
            {
                (
                    TranscriptSearchItemKind::Diff,
                    format!("Diff / {}", entry.title),
                    entry.diff.clone(),
                )
            } else if self.transcript_search.include_tools {
                let prefix = match entry.kind {
                    TimelineEntryKind::Phase => "Phase",
                    TimelineEntryKind::ToolCall => "Tool call",
                    TimelineEntryKind::ToolResult => "Tool result",
                    TimelineEntryKind::Permission => "Review",
                    TimelineEntryKind::Diff => "Diff",
                    TimelineEntryKind::Cost => "Cost",
                    TimelineEntryKind::Note => "Note",
                };
                (
                    TranscriptSearchItemKind::Tool,
                    format!("{prefix} / {}", entry.title),
                    String::new(),
                )
            } else {
                continue;
            };

            items.push(TranscriptSearchItem {
                kind,
                label,
                detail: if let Some(summary) = &entry.review_summary {
                    let mut detail = vec![entry.detail.clone()];
                    detail.extend(summary.files.iter().map(|file| file.summary_line()));
                    detail.join("\n")
                } else {
                    entry.detail.clone()
                },
                paths: entry.paths.clone(),
                diff,
                timestamp: entry.timestamp,
            });
        }

        items.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
        if query.is_empty() {
            items.truncate(120);
            return items;
        }

        items
            .into_iter()
            .filter(|item| {
                item.label.to_lowercase().contains(&query)
                    || item.detail.to_lowercase().contains(&query)
                    || item
                        .paths
                        .iter()
                        .any(|path| path.to_lowercase().contains(&query))
                    || item.diff.to_lowercase().contains(&query)
            })
            .take(120)
            .collect()
    }

    pub fn remember_recent_edit(&mut self, path: &str) {
        let normalized = path.to_string();
        self.recent_edited_files
            .retain(|entry| entry != &normalized);
        self.recent_edited_files.push_front(normalized.clone());
        while self.recent_edited_files.len() > 12 {
            self.recent_edited_files.pop_back();
        }
        self.resume_dashboard.recent_edits =
            self.recent_edited_files.iter().take(5).cloned().collect();
        self.update_welcome();
    }

    pub fn remember_recent_prompt(&mut self, prompt: &str) {
        if prompt.trim().is_empty() {
            return;
        }
        let normalized = prompt.trim().to_string();
        self.recent_prompts.retain(|entry| entry != &normalized);
        self.recent_prompts.push_front(normalized);
        while self.recent_prompts.len() > 20 {
            self.recent_prompts.pop_back();
        }
    }

    pub fn remember_recent_checkpoint(&mut self, checkpoint_id: &str) {
        if checkpoint_id.trim().is_empty() {
            return;
        }
        let normalized = checkpoint_id.trim().to_string();
        self.recent_checkpoints.retain(|entry| entry != &normalized);
        self.recent_checkpoints.push_front(normalized.clone());
        while self.recent_checkpoints.len() > 12 {
            self.recent_checkpoints.pop_back();
        }
        self.resume_dashboard.recent_checkpoints =
            self.recent_checkpoints.iter().take(5).cloned().collect();
        self.update_welcome();
    }

    pub fn set_resume_dashboard(&mut self, dashboard: ResumeDashboardState) {
        self.resume_dashboard = dashboard;
        self.update_welcome();
    }

    pub fn open_info_popup(&mut self, title: impl Into<String>, content: impl Into<String>) {
        self.info_popup_title = title.into();
        self.info_popup_content = content.into();
        self.info_popup_scroll = 0;
        self.mode = AppMode::InfoPopup;
    }

    pub fn close_info_popup(&mut self) {
        self.info_popup_title.clear();
        self.info_popup_content.clear();
        self.info_popup_scroll = 0;
        self.mode = AppMode::Normal;
    }

    pub fn scroll_info_popup_up(&mut self, amount: u16) {
        self.info_popup_scroll = self.info_popup_scroll.saturating_sub(amount);
    }

    pub fn scroll_info_popup_down(&mut self, amount: u16) {
        self.info_popup_scroll = self.info_popup_scroll.saturating_add(amount);
    }

    /// Clear status if it's older than 3 seconds.
    pub fn clear_old_status(&mut self) {
        if let Some((_, when)) = &self.status_message {
            if when.elapsed().as_secs() > 3 {
                self.status_message = None;
            }
        }
    }

    pub fn next_request_id(&mut self) -> String {
        self.request_id_counter += 1;
        format!("req-{}", self.request_id_counter)
    }

    pub fn start_streaming_message(&mut self) {
        let idx = self.messages.len();
        self.messages.push(ChatMessage::assistant(""));
        self.streaming_message = Some(idx);
        self.current_iteration = 0;
        self.turn_input_tokens = 0;
        self.turn_output_tokens = 0;
        self.scroll_offset = 0;
    }

    pub fn append_streaming_chunk(&mut self, chunk: &str) {
        if let Some(idx) = self.streaming_message {
            if let Some(msg) = self.messages.get_mut(idx) {
                msg.content.push_str(chunk);
            }
        }
        if self.scroll_offset <= 1 {
            self.scroll_offset = 0;
        }
    }

    pub fn finalize_streaming(&mut self) {
        if let Some(idx) = self.streaming_message {
            if let Some(msg) = self.messages.get(idx) {
                self.record_assistant_output(&msg.content.clone());
            }
        }
        self.streaming_message = None;
        self.active_tool = None;
        self.scroll_offset = 0;
    }

    pub fn set_plan(&mut self, steps: Vec<String>, original_request: String) {
        self.set_plan_review(steps, original_request, String::new(), String::new(), false);
    }

    pub fn set_plan_review(
        &mut self,
        steps: Vec<String>,
        original_request: String,
        summary: String,
        prompt_id: String,
        is_execution_gate: bool,
    ) {
        self.plan_steps = steps
            .into_iter()
            .map(|s| PlanStep {
                description: s,
                status: PlanStepStatus::Pending,
            })
            .collect();
        self.plan_current_step = 0;
        self.plan_original_request = original_request;
        self.plan_summary = summary;
        self.plan_prompt_id = prompt_id;
        self.plan_is_execution_gate = is_execution_gate;
        self.mode = AppMode::PlanReview;
    }

    pub fn advance_plan_step(&mut self) {
        if self.plan_current_step < self.plan_steps.len() {
            self.plan_steps[self.plan_current_step].status = PlanStepStatus::Done;
            self.plan_current_step += 1;
        }
    }

    pub fn current_plan_step_description(&self) -> Option<&str> {
        self.plan_steps
            .get(self.plan_current_step)
            .map(|s| s.description.as_str())
    }

    pub fn clear_plan(&mut self) {
        self.plan_steps.clear();
        self.plan_current_step = 0;
        self.plan_original_request.clear();
        self.plan_summary.clear();
        self.plan_prompt_id.clear();
        self.plan_is_execution_gate = false;
    }

    pub fn push_suggestion(&mut self, sender: String, text: String) {
        self.suggestions.push_back(Suggestion {
            sender,
            text,
            received_at: Instant::now(),
        });
        while self.suggestions.len() > SUGGESTION_MAX {
            self.suggestions.pop_front();
        }
    }

    pub fn clear_old_suggestions(&mut self) {
        let now = Instant::now();
        while self
            .suggestions
            .front()
            .is_some_and(|s| now.duration_since(s.received_at) > SUGGESTION_TTL)
        {
            self.suggestions.pop_front();
        }
    }

    pub fn latest_suggestion(&self) -> Option<&Suggestion> {
        self.suggestions
            .back()
            .filter(|s| s.received_at.elapsed() < SUGGESTION_HINT_TTL)
    }

    pub fn reset_pair_state(&mut self) {
        self.pair_mode_active = false;
        self.pair_short_code.clear();
        self.pair_invite_code.clear();
        self.pair_is_host = false;
        self.connected_users.clear();
        self.suggestions.clear();
    }

    pub fn record_user_input(&mut self, text: &str) {
        self.session_requests += 1;
        self.input_chars += text.len();
        self.input_tokens_estimate += text.len() / 4;
        self.last_user_message = Some(text.to_string());
    }

    pub fn record_assistant_output(&mut self, text: &str) {
        self.output_chars += text.len();
        self.output_tokens_estimate += text.len() / 4;
    }

    pub fn session_summary_text(&self) -> String {
        let elapsed = self.session_started_at.elapsed();
        let total_seconds = elapsed.as_secs();
        let mins = total_seconds / 60;
        let secs = total_seconds % 60;
        let duration = if mins > 0 {
            format!("{mins}m {secs}s")
        } else {
            format!("{secs}s")
        };

        format!(
            "Session Summary\n\
Provider: {} ({})\n\
Duration: {}\n\
Requests: {}\n\
Input: {} chars (~{} tokens)\n\
Output: {} chars (~{} tokens)",
            self.provider_name,
            self.model_name,
            duration,
            self.session_requests,
            self.input_chars,
            self.input_tokens_estimate,
            self.output_chars,
            self.output_tokens_estimate
        )
    }
}

fn redact_sensitive_history_command(raw: &str) -> String {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return String::new();
    }

    let mut parts = trimmed.split_whitespace();
    let Some(command) = parts.next() else {
        return String::new();
    };
    let command_lower = command.to_ascii_lowercase();

    if command_lower == "/api-key" || command_lower == "/set-api-key" {
        if let Some(provider) = parts.next() {
            if parts.next().is_some() {
                return format!("{command} {provider} <redacted>");
            }
        }
        return trimmed.to_string();
    }

    if command_lower == "/set" {
        let key = parts.next().unwrap_or("");
        if key == "api_keys" || key.starts_with("api_keys.") {
            return format!("{command} {key} <redacted>");
        }
    }

    trimmed.to_string()
}

#[cfg(test)]
mod tests {
    use super::{
        parse_mutation_review_chunks, ApprovedReviewChunk, MutationReviewChunk,
        MutationReviewState, ReviewDecisionState, ThemeMode,
    };

    #[test]
    fn theme_mode_parses_user_values() {
        assert_eq!(ThemeMode::from_user_input("dark"), Some(ThemeMode::Dark));
        assert_eq!(ThemeMode::from_user_input("light"), Some(ThemeMode::Light));
        assert_eq!(ThemeMode::from_user_input("default"), None);
    }

    #[test]
    fn theme_mode_normalizes_config_values() {
        assert_eq!(ThemeMode::from_ui_theme("light"), ThemeMode::Light);
        assert_eq!(ThemeMode::from_ui_theme("dark"), ThemeMode::Dark);
        assert_eq!(ThemeMode::from_ui_theme("default"), ThemeMode::Dark);
        assert_eq!(ThemeMode::from_ui_theme("minimal"), ThemeMode::Dark);
        assert_eq!(ThemeMode::from_ui_theme("unknown"), ThemeMode::Dark);
    }

    #[test]
    fn parse_mutation_review_chunks_extracts_per_file_hunks() {
        let diff = "\
diff --git a/src/demo.rs b/src/demo.rs
--- a/src/demo.rs
+++ b/src/demo.rs
@@ -1 +1 @@
-old
+new
diff --git a/src/other.rs b/src/other.rs
--- a/src/other.rs
+++ b/src/other.rs
@@ -3 +3 @@
-left
+right
";

        let chunks = parse_mutation_review_chunks(
            diff,
            &[
                "/tmp/src/demo.rs".to_string(),
                "/tmp/src/other.rs".to_string(),
            ],
        );

        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[0].path, "/tmp/src/demo.rs");
        assert_eq!(chunks[0].hunk_index, 0);
        assert_eq!(chunks[1].path, "/tmp/src/other.rs");
        assert_eq!(chunks[1].hunk_index, 0);
    }

    #[test]
    fn mutation_review_file_groups_preserve_file_order_and_counts() {
        let review = MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec![
                "/tmp/src/demo.rs".to_string(),
                "/tmp/src/other.rs".to_string(),
            ],
            diff: String::new(),
            checkpoint_id: None,
            changed: Some(true),
            message: String::new(),
            selected_path_index: 0,
            chunks: vec![
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: true,
                },
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 1,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
                MutationReviewChunk {
                    path: "/tmp/src/other.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -8 +8 @@".to_string(),
                    diff: "@@ -8 +8 @@\n-before\n+after".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 0,
        };

        let groups = review.file_groups();

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0].path, "/tmp/src/demo.rs");
        assert_eq!(groups[0].chunk_indexes, vec![0, 1]);
        assert_eq!(groups[0].selected_chunks, 1);
        assert_eq!(groups[1].path, "/tmp/src/other.rs");
        assert_eq!(groups[1].chunk_indexes, vec![2]);
        assert_eq!(groups[1].selected_chunks, 0);
    }

    #[test]
    fn mutation_review_partial_chunk_summary_tracks_accept_and_reject_lines() {
        let review = MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec![
                "/tmp/src/demo.rs".to_string(),
                "/tmp/src/other.rs".to_string(),
            ],
            diff: String::new(),
            checkpoint_id: None,
            changed: Some(true),
            message: String::new(),
            selected_path_index: 0,
            chunks: vec![
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: false,
                },
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 1,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
                MutationReviewChunk {
                    path: "/tmp/src/other.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -8 +8 @@".to_string(),
                    diff: "@@ -8 +8 @@\n-before\n+after".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 0,
        };

        let summary = review.build_decision_summary(
            true,
            &[],
            &[ApprovedReviewChunk {
                path: "/tmp/src/demo.rs".to_string(),
                hunk_index: 1,
            }],
        );

        assert_eq!(summary.headline(), "Accepted 1/3 hunks across 1/2 files");
        assert_eq!(summary.files.len(), 2);
        assert_eq!(summary.files[0].state, ReviewDecisionState::Partial);
        assert_eq!(
            summary.files[0].summary_line(),
            "/tmp/src/demo.rs: accepted h2; rejected h1"
        );
        assert_eq!(summary.files[1].state, ReviewDecisionState::Rejected);
        assert_eq!(
            summary.files[1].summary_line(),
            "/tmp/src/other.rs: rejected hunks h1"
        );
    }
}
