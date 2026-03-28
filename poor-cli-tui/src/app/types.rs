use super::review::{MutationReviewState, ReviewDecisionSummary};
use std::collections::{HashMap, VecDeque};
use std::time::{Duration, Instant};

// ── Pair mode types ─────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PairRole {
    Driver,
    Navigator,
    Reviewer,
}

impl PairRole {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Driver => "DRV",
            Self::Navigator => "NAV",
            Self::Reviewer => "REV",
        }
    }
    pub fn from_ui_role(role: &str) -> Self {
        match role {
            "driver" | "prompter" => Self::Driver,
            "reviewer" => Self::Reviewer,
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

#[derive(Debug, Clone, Default)]
pub struct CollaborationAgendaItem {
    pub item_id: String,
    pub text: String,
    pub author: String,
    pub resolved: bool,
}

#[derive(Debug, Clone, Default)]
pub struct MultiplayerState {
    pub enabled: bool,
    pub room: String,
    pub role: String,
    pub ui_role: String,
    pub mode: String,
    pub connection_id: String,
    pub display_name: String,
    pub approval_state: String,
    pub hand_raised: bool,
    pub queue_position: u64,
    pub remote_invite: String,
    pub queue_depth: u64,
    pub member_count: u64,
    pub active_connection_id: String,
    pub lobby_enabled: bool,
    pub preset: String,
    pub member_roles: Vec<String>,
    pub agenda: Vec<CollaborationAgendaItem>,
    pub agenda_open_count: u64,
    pub agenda_total_count: u64,
}

pub const SUGGESTION_HINT_TTL: Duration = Duration::from_secs(15);

#[derive(Debug, Clone, Default)]
pub struct PairState {
    pub mode_active: bool,
    pub short_code: String,
    pub invite_code: String,
    pub is_host: bool,
    pub connected_users: Vec<PairUser>,
    pub suggestions: VecDeque<Suggestion>,
}

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
    ApprovalRequest { tool_name: String },
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

    pub fn approval_request(tool_name: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::ApprovalRequest { tool_name: tool_name.into() },
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

#[derive(Debug, Clone)]
pub enum TimelineEntryKind {
    Phase,
    ToolCall,
    ToolResult,
    Permission,
    Diff,
    Cost,
    Note,
    Checkpoint,
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
pub struct AtPathCompletionItem {
    pub path: String,
    pub detail: String,
}

#[derive(Debug, Clone, Default)]
pub struct AtPathCompletionState {
    pub active: bool,
    pub query: String,
    pub token_start: usize,
    pub token_end: usize,
    pub selected_index: usize,
    pub quoted: bool,
    pub quote_char: char,
    pub items: Vec<AtPathCompletionItem>,
}

#[derive(Debug, Clone, Default)]
pub struct QueueManagerState {
    pub selected_index: usize,
}

#[derive(Debug, Clone, Default)]
pub struct ApiKeyEditorField {
    pub label: String,
    pub provider: Option<String>,
    pub env_var: String,
    pub help: String,
    pub value: String,
}

#[derive(Debug, Clone, Default)]
pub struct ApiKeyEditorState {
    pub env_path: String,
    pub template_path: String,
    pub env_exists: bool,
    pub selected_index: usize,
    pub cursor: usize,
    pub fields: Vec<ApiKeyEditorField>,
    pub status: String,
    pub error: String,
    pub init_error: String,
    pub target_provider: String,
    pub target_model: String,
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

// ── Application state ────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum AppMode {
    Normal,          // includes Command (/ prefix detection)
    Overlay,         // ProviderSelect, InfoPopup, ApiKeyEditor, JoinWizard
    QuickOpen,       // Ctrl+P palette
    InlineApproval,  // pending y/n/d in chat stream
    Quitting,
}

#[derive(Debug, Clone, PartialEq)]
pub enum OverlayKind {
    ProviderSelect,
    InfoPopup,
    ApiKeyEditor,
    JoinWizard,
    GraphOverlay,
    ListSelector,
    Onboarding,
}

#[derive(Debug, Clone)]
pub struct ListSelectorItem {
    pub label: String, // display text
    pub value: String, // ID/name passed to the action command
}

#[derive(Debug, Clone)]
pub struct ListSelectorState {
    pub title: String,
    pub items: Vec<ListSelectorItem>,
    pub selected_idx: usize,
    pub command_template: String, // e.g. "/undo {}" — {} replaced with selected value
    pub action_hint_override: Option<String>, // custom footer hint for this list
}

#[derive(Debug, Clone)]
pub struct GraphOverlayState {
    pub active: bool,
    pub started_at: Instant,
    pub status_text: String,
    pub progress_pct: u8,
    pub completed_at: Option<Instant>,
    pub nodes: Vec<(String, Vec<String>)>, // (dir_name, children)
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

#[derive(Debug, Clone, Default)]
pub struct PlanState {
    pub steps: Vec<PlanStep>,
    pub current_step: usize,
    pub original_request: String,
    pub summary: String,
    pub prompt_id: String,
    pub is_execution_gate: bool,
    pub review_read_only: bool,
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
    Dark,           // one-dark style (default dark)
    Light,          // github-light style (default light)
    Dracula,        // dracula purple
    Nord,           // nord blue
    Monokai,        // monokai warm
    GithubDark,     // github dark dimmed
    SolarizedLight, // solarized light
    QuietLight,     // quiet light muted
}

impl ThemeMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Dark => "dark",
            Self::Light => "light",
            Self::Dracula => "dracula",
            Self::Nord => "nord",
            Self::Monokai => "monokai",
            Self::GithubDark => "github-dark",
            Self::SolarizedLight => "solarized-light",
            Self::QuietLight => "quiet-light",
        }
    }

    pub const fn is_dark(self) -> bool {
        matches!(self, Self::Dark | Self::Dracula | Self::Nord | Self::Monokai | Self::GithubDark)
    }

    pub fn all_themes() -> &'static [ThemeMode] {
        &[
            Self::Dark, Self::Light, Self::Dracula, Self::Nord,
            Self::Monokai, Self::GithubDark, Self::SolarizedLight, Self::QuietLight,
        ]
    }

    pub fn from_ui_theme(value: &str) -> Self {
        match value.trim().to_lowercase().as_str() {
            "light" | "github-light" => Self::Light,
            "dracula" => Self::Dracula,
            "nord" => Self::Nord,
            "monokai" => Self::Monokai,
            "github-dark" => Self::GithubDark,
            "solarized-light" => Self::SolarizedLight,
            "quiet-light" => Self::QuietLight,
            "dark" | "one-dark" | "default" | "minimal" | "" => Self::Dark,
            _ => Self::Dark,
        }
    }

    pub fn from_user_input(value: &str) -> Option<Self> {
        match value.trim().to_lowercase().as_str() {
            "dark" | "one-dark" => Some(Self::Dark),
            "light" | "github-light" => Some(Self::Light),
            "dracula" => Some(Self::Dracula),
            "nord" => Some(Self::Nord),
            "monokai" => Some(Self::Monokai),
            "github-dark" => Some(Self::GithubDark),
            "solarized-light" => Some(Self::SolarizedLight),
            "quiet-light" => Some(Self::QuietLight),
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
    pub ready: bool,
    pub status_label: String,
    pub models: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderSelectPane {
    Providers,
    Models,
}

#[derive(Default)]
pub struct TokenTracking {
    pub turn_input_tokens: u64,
    pub turn_output_tokens: u64,
    pub cumulative_input_tokens: u64,
    pub cumulative_output_tokens: u64,
}

pub struct StreamingState {
    pub message: Option<usize>, // index of in-progress assistant message
    pub thinking_buffer: String, // accumulated thinking/reasoning text
    pub thinking_active: bool, // true while thinking content is streaming
    pub current_iteration: u32,
    pub iteration_cap: u32,
    pub active_tool: Option<String>,
    pub request_id_counter: u64,
    pub active_request_id: String,
    pub active_request_started_at: Option<Instant>,
}
impl Default for StreamingState {
    fn default() -> Self {
        Self {
            message: None,
            thinking_buffer: String::new(),
            thinking_active: false,
            current_iteration: 0,
            iteration_cap: 25,
            active_tool: None,
            request_id_counter: 0,
            active_request_id: String::new(),
            active_request_started_at: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ProviderState {
    pub name: String,
    pub model: String,
    pub capabilities: Vec<String>,
    pub list: Vec<ProviderEntry>,
    pub select_idx: usize,
    pub select_pane: ProviderSelectPane,
    pub model_select_indices: HashMap<String, usize>,
}
impl Default for ProviderState {
    fn default() -> Self {
        Self {
            name: "unknown".into(),
            model: "unknown".into(),
            capabilities: Vec::new(),
            list: Vec::new(),
            select_idx: 0,
            select_pane: ProviderSelectPane::Providers,
            model_select_indices: HashMap::new(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ApprovalState {
    pub request_id: String,
    pub tool_name: String,
    pub operation: String,
    pub prompt_id: String,
    pub paths: Vec<String>,
    pub diff: String,
    pub message: String,
    pub checkpoint_id: Option<String>,
    pub changed: Option<bool>,
    pub diff_expanded: bool,
    pub mutation_review: Option<MutationReviewState>,
}
