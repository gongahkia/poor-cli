/// Application state machine for the poor-cli TUI.
pub mod review;
pub use review::{
    ApprovedReviewChunk, MutationReviewChunk, MutationReviewFileGroup, MutationReviewState,
    ReviewDecisionFileSummary, ReviewDecisionState, ReviewDecisionSummary,
    parse_mutation_review_chunks,
};
mod types;
pub use types::*;

use crate::helpers::should_skip_dir;
use std::collections::{HashSet, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

const SUGGESTION_TTL: Duration = Duration::from_secs(30);
const SUGGESTION_MAX: usize = 10;

pub struct App {
    // ── Chat state ───
    pub messages: Vec<ChatMessage>,
    pub input_buffer: String,
    pub input_cursor: usize,

    // ── Scroll ───
    pub scroll_offset: u16,

    // ── Mode ───
    pub mode: AppMode,
    pub overlay_kind: Option<OverlayKind>,
    // ── Provider info ───
    pub provider: ProviderState,
    pub info_popup_title: String,
    pub info_popup_content: String,
    pub info_popup_scroll: u16,
    pub info_popup_selected_idx: usize,
    pub info_popup_return_mode: Option<AppMode>,
    pub api_key_editor: Option<ApiKeyEditorState>,
    pub list_selector: Option<ListSelectorState>,
    pub startup_first_launch: bool,

    // ── Session info ───
    pub streaming_enabled: bool,
    pub version: String,

    // ── Waiting / spinner ───
    pub waiting: bool,
    pub spinner_tick: usize,
    pub wait_start: Option<Instant>,

    // ── Prompt queue (steering harness) ───
    pub prompt_queue: VecDeque<QueuedPrompt>,
    pub queue_paused: bool,

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
    pub permission_review_read_only: bool,
    pub mutation_review: Option<MutationReviewState>,
    pub pending_approval: Option<ApprovalState>,
    pub context_inspector: Option<ContextInspectorState>,
    pub quick_open: QuickOpenState,
    pub at_path_completion: AtPathCompletionState,
    pub queue_manager: QueueManagerState,
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
    pub mascot_enabled: bool,
    pub onboarding_active: bool,
    pub onboarding_step: usize,
    pub onboarding_total_steps: usize,
    pub onboarding_try_now: String,
    pub onboarding_step_title: String,
    pub onboarding_step_objective: String,
    pub onboarding_step_commands: Vec<String>,
    pub onboarding_owl_lines: Vec<String>,
    pub onboarding_owl_speech: String,
    pub join_wizard_active: bool,
    pub join_wizard_step: u8,
    pub join_wizard_input: String,
    pub join_wizard_error: String,
    pub autopilot_enabled: bool,
    pub last_command_output: Option<String>,
    pub execution_profile: String,
    pub context_budget_tokens: usize,
    pub context_budget_files: Vec<String>,
    pub context_budget_estimated_tokens: usize,
    pub last_mutation_checkpoint_id: Option<String>,
    pub pending_restore_checkpoint_id: Option<String>,
    pub last_mutation_diff: String,
    pub recent_edited_files: VecDeque<String>,
    pub recent_prompts: VecDeque<String>,
    pub recent_checkpoints: VecDeque<String>,
    pub git_branch: String,
    pub git_dirty: bool,
    pub resume_dashboard: ResumeDashboardState,
    pub qa_mode_enabled: bool,
    pub qa_command: String,
    pub multiplayer: MultiplayerState,

    // ── Streaming / agentic state ───
    pub streaming: StreamingState,

    // ── Plan mode state ───
    pub plan: PlanState,

    // ── Real token tracking (from server) ───
    pub tokens: TokenTracking,
    pub response_mode: ResponseMode,
    pub theme_mode: ThemeMode,
    pub compact_select_idx: usize,

    // ── Reconnect message tracking ───
    pub reconnect_message_idx: Option<usize>,

    // ── Pair mode state ───
    pub pair: PairState,

    // ── Graph overlay (repo indexing animation) ───
    pub graph_overlay: GraphOverlayState,
}

impl Default for App {
    fn default() -> Self {
        Self {
            messages: Vec::new(),
            input_buffer: String::new(),
            input_cursor: 0,
            scroll_offset: 0,
            mode: AppMode::Normal,
            overlay_kind: None,
            provider: ProviderState::default(),
            info_popup_title: String::new(),
            info_popup_content: String::new(),
            info_popup_scroll: 0,
            info_popup_selected_idx: 0,
            info_popup_return_mode: None,
            api_key_editor: None,
            list_selector: None,
            startup_first_launch: false,
            streaming_enabled: true,
            version: "0.4.0".into(),
            waiting: false,
            spinner_tick: 0,
            wait_start: None,
            prompt_queue: VecDeque::new(),
            queue_paused: false,
            command_history: VecDeque::with_capacity(100),
            history_index: None,
            command_match_index: 0,
            permission_message: String::new(),
            permission_answer: None,
            permission_prompt_id: String::new(),
            permission_approved_paths: Vec::new(),
            permission_approved_chunks: Vec::new(),
            permission_review_read_only: false,
            mutation_review: None,
            pending_approval: None,
            context_inspector: None,
            quick_open: QuickOpenState::default(),
            at_path_completion: AtPathCompletionState::default(),
            queue_manager: QueueManagerState::default(),
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
            mascot_enabled: true,
            onboarding_active: false,
            onboarding_step: 0,
            onboarding_total_steps: 0,
            onboarding_try_now: String::new(),
            onboarding_step_title: String::new(),
            onboarding_step_objective: String::new(),
            onboarding_step_commands: Vec::new(),
            onboarding_owl_lines: Vec::new(),
            onboarding_owl_speech: String::new(),
            join_wizard_active: false,
            join_wizard_step: 0,
            join_wizard_input: String::new(),
            join_wizard_error: String::new(),
            autopilot_enabled: false,
            last_command_output: None,
            execution_profile: "safe".to_string(),
            context_budget_tokens: 6000,
            context_budget_files: Vec::new(),
            context_budget_estimated_tokens: 0,
            last_mutation_checkpoint_id: None,
            pending_restore_checkpoint_id: None,
            last_mutation_diff: String::new(),
            recent_edited_files: VecDeque::new(),
            recent_prompts: VecDeque::new(),
            recent_checkpoints: VecDeque::new(),
            git_branch: String::new(),
            git_dirty: false,
            resume_dashboard: ResumeDashboardState::default(),
            qa_mode_enabled: false,
            qa_command: String::new(),
            multiplayer: MultiplayerState::default(),
            streaming: StreamingState::default(),
            plan: PlanState::default(),
            tokens: TokenTracking::default(),
            response_mode: ResponseMode::Rich,
            theme_mode: ThemeMode::Dark,
            compact_select_idx: 0,
            reconnect_message_idx: None,
            pair: PairState::default(),
            graph_overlay: GraphOverlayState {
                active: false,
                started_at: Instant::now(),
                status_text: String::new(),
                progress_pct: 0,
                completed_at: None,
                nodes: Vec::new(),
            },
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
        let provider_known =
            !self.provider.name.trim().is_empty() && self.provider.name != "unknown";
        let model_known = !self.provider.model.trim().is_empty() && self.provider.model != "unknown";
        let provider_summary = match (provider_known, model_known) {
            (true, true) => format!(
                "{} · {} · {}",
                self.provider.model, self.provider.name, self.permission_mode_label
            ),
            (true, false) => format!("{} · {}", self.provider.name, self.permission_mode_label),
            _ => format!(
                "provider selection pending · {}",
                self.permission_mode_label
            ),
        };
        let last_session_line = if self.resume_dashboard.last_session_summary.is_empty() {
            String::new()
        } else {
            format!(
                "\nlast session  {}",
                self.resume_dashboard.last_session_summary
            )
        };
        let setup_line = if self.server_connected {
            String::new()
        } else {
            "\n/setup configures API keys and creates .env".to_string()
        };
        let logo = r#" ____   ___   ___  ____        ____ _     ___
|  _ \ / _ \ / _ \|  _ \      / ___| |   |_ _|
| |_) | | | | | | | |_) |    | |   | |    | |
|  __/| |_| | |_| |  _ <     | |___| |___ | |
|_|    \___/ \___/|_| \_\     \____|_____|___|"#;
        let mascot_line = if self.mascot_enabled {
            "\n\n  {o,o}   Welcome! Type /onboarding if you're new here.\n  /)__)\n  -\"-\"-"
        } else {
            ""
        };
        format!(
            "{logo}\n\n\
             poor-cli (v{version})\n\
             {provider_summary}\n\
             {workspace}\n\n\
             ? for shortcuts{setup_line}{last_session_line}{mascot_line}",
            version = self.version,
            provider_summary = provider_summary,
            workspace = workspace,
            setup_line = setup_line,
            last_session_line = last_session_line,
            mascot_line = mascot_line,
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

    pub fn open_provider_select(&mut self) {
        self.graph_overlay.active = false; // dismiss graph overlay if active
        self.provider.select_pane = ProviderSelectPane::Providers;
        self.provider.select_idx = self
            .provider
            .list
            .iter()
            .position(|provider| provider.name.eq_ignore_ascii_case(&self.provider.name))
            .unwrap_or(0)
            .min(self.provider.list.len().saturating_sub(1));
        self.ensure_provider_model_selection();
        self.mode = AppMode::Overlay;
        self.overlay_kind = Some(OverlayKind::ProviderSelect);
    }

    pub fn selected_provider(&self) -> Option<&ProviderEntry> {
        self.provider.list.get(self.provider.select_idx)
    }

    pub fn selected_provider_model_index(&self) -> Option<usize> {
        let provider = self.selected_provider()?;
        if provider.models.is_empty() {
            return None;
        }
        let selected = self
            .provider
            .model_select_indices
            .get(&provider.name)
            .copied()
            .unwrap_or_else(|| self.default_provider_model_index(provider));
        Some(selected.min(provider.models.len().saturating_sub(1)))
    }

    pub fn selected_provider_model(&self) -> Option<String> {
        let provider = self.selected_provider()?;
        if provider.models.is_empty() {
            if provider.name.eq_ignore_ascii_case(&self.provider.name)
                && !self.provider.model.trim().is_empty()
                && self.provider.model != "unknown"
            {
                return Some(self.provider.model.clone());
            }
            return None;
        }
        let idx = self.selected_provider_model_index()?;
        provider.models.get(idx).cloned()
    }

    pub fn selected_provider_switch_model(&self) -> Option<String> {
        let provider = self.selected_provider()?;
        if provider.models.is_empty() {
            return None;
        }
        self.selected_provider_model()
    }

    pub fn move_provider_selection(&mut self, forward: bool) -> bool {
        if self.provider.list.is_empty() {
            return false;
        }
        let next_idx = if forward {
            (self.provider.select_idx + 1).min(self.provider.list.len().saturating_sub(1))
        } else {
            self.provider.select_idx.saturating_sub(1)
        };
        if next_idx == self.provider.select_idx {
            return false;
        }
        self.provider.select_idx = next_idx;
        self.ensure_provider_model_selection();
        if self
            .selected_provider()
            .is_some_and(|provider| provider.models.is_empty())
            && self.provider.select_pane == ProviderSelectPane::Models
        {
            self.provider.select_pane = ProviderSelectPane::Providers;
        }
        true
    }

    pub fn move_provider_model_selection(&mut self, forward: bool) -> bool {
        let provider = match self.selected_provider() {
            Some(provider) if !provider.models.is_empty() => provider,
            _ => return false,
        };
        let provider_name = provider.name.clone();
        let models_len = provider.models.len();
        let current = self
            .selected_provider_model_index()
            .unwrap_or_else(|| self.default_provider_model_index(provider));
        let next = if forward {
            (current + 1).min(models_len.saturating_sub(1))
        } else {
            current.saturating_sub(1)
        };
        if next == current {
            return false;
        }
        self.provider.model_select_indices
            .insert(provider_name, next);
        true
    }

    pub fn focus_provider_models(&mut self) -> bool {
        if self
            .selected_provider()
            .is_some_and(|provider| !provider.models.is_empty())
        {
            self.ensure_provider_model_selection();
            self.provider.select_pane = ProviderSelectPane::Models;
            true
        } else {
            false
        }
    }

    pub fn focus_provider_list(&mut self) -> bool {
        if self.provider.select_pane == ProviderSelectPane::Providers {
            return false;
        }
        self.provider.select_pane = ProviderSelectPane::Providers;
        true
    }

    fn ensure_provider_model_selection(&mut self) {
        let provider = match self.selected_provider() {
            Some(provider) if !provider.models.is_empty() => provider,
            _ => return,
        };
        let provider_name = provider.name.clone();
        let max_index = provider.models.len().saturating_sub(1);
        let default_idx = self.default_provider_model_index(provider);
        let entry = self
            .provider
            .model_select_indices
            .entry(provider_name)
            .or_insert(default_idx);
        *entry = (*entry).min(max_index);
    }

    fn default_provider_model_index(&self, provider: &ProviderEntry) -> usize {
        if provider.name.eq_ignore_ascii_case(&self.provider.name)
            && !self.provider.model.trim().is_empty()
            && self.provider.model != "unknown"
        {
            provider
                .models
                .iter()
                .position(|model| model == &self.provider.model)
                .unwrap_or(0)
        } else {
            0
        }
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
        // graph overlay: user must press Esc to dismiss (handled in input/mod.rs)
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
        self.at_path_completion = AtPathCompletionState::default();

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
        // render context inspector data as InfoPopup overlay
        let mut lines = vec![format!(
            "**Context Inspector** — {} files, ~{} tokens (budget: {})",
            state.files.len(), state.total_tokens, state.budget_tokens
        )];
        if state.truncated {
            lines.push("(context truncated)".to_string());
        }
        if !state.message.is_empty() {
            lines.push(format!("\n{}", state.message));
        }
        lines.push(String::new());
        for file in &state.files {
            lines.push(format!(
                "- `{}` [{}] ~{} tok — {}",
                file.path, file.source, file.estimated_tokens, file.reason
            ));
        }
        self.context_inspector = Some(state);
        self.open_info_popup("Context Inspector", lines.join("\n"));
    }

    pub fn close_context_inspector(&mut self) {
        self.context_inspector = None;
        self.close_info_popup();
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
        self.mode = AppMode::InlineApproval;
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
        self.overlay_kind = None;
    }

    pub fn close_quick_open(&mut self) {
        self.quick_open = QuickOpenState::default();
        self.mode = AppMode::Normal;
        self.overlay_kind = None;
    }

    pub fn refresh_at_path_completion(&mut self) {
        self.at_path_completion = build_at_path_completion_state(self).unwrap_or_default();
    }

    pub fn clear_at_path_completion(&mut self) {
        self.at_path_completion = AtPathCompletionState::default();
    }

    pub fn move_at_path_selection(&mut self, forward: bool) -> bool {
        if !self.at_path_completion.active || self.at_path_completion.items.is_empty() {
            return false;
        }

        let item_count = self.at_path_completion.items.len();
        if forward {
            self.at_path_completion.selected_index =
                (self.at_path_completion.selected_index + 1) % item_count;
        } else if self.at_path_completion.selected_index == 0 {
            self.at_path_completion.selected_index = item_count - 1;
        } else {
            self.at_path_completion.selected_index -= 1;
        }
        true
    }

    pub fn accept_at_path_completion(&mut self) -> bool {
        if !self.at_path_completion.active {
            return false;
        }

        let Some(item) = self
            .at_path_completion
            .items
            .get(
                self.at_path_completion
                    .selected_index
                    .min(self.at_path_completion.items.len().saturating_sub(1)),
            )
            .cloned()
        else {
            return false;
        };

        let replacement = render_at_path_token(
            &item.path,
            self.at_path_completion.quoted,
            self.at_path_completion.quote_char,
        );
        let token_start = self.at_path_completion.token_start;
        let token_end = self
            .at_path_completion
            .token_end
            .min(self.input_buffer.len());
        let suffix_char = self.input_buffer[token_end..].chars().next();
        let needs_space = suffix_char.is_none_or(|ch| {
            !ch.is_whitespace() && !matches!(ch, ',' | ';' | ':' | ')' | ']' | '}')
        });
        let inserted = if needs_space {
            format!("{replacement} ")
        } else {
            replacement
        };

        self.input_buffer
            .replace_range(token_start..token_end, inserted.as_str());
        self.input_cursor = token_start + inserted.len();
        self.refresh_at_path_completion();
        true
    }

    pub fn open_queue_manager(&mut self) {
        // render queue contents as InfoPopup
        let mut lines = vec!["**Prompt Queue**".to_string()];
        if self.prompt_queue.is_empty() {
            lines.push("(empty)".to_string());
        } else {
            for (i, prompt) in self.prompt_queue.iter().enumerate() {
                lines.push(format!("{}. [{}] {}", i + 1, prompt.source, prompt.display));
            }
        }
        if self.queue_paused {
            lines.push(String::new());
            lines.push("Queue is paused. Use `/queue resume` to continue.".to_string());
        }
        self.open_info_popup("Queue", lines.join("\n"));
    }

    pub fn close_queue_manager(&mut self) {
        self.queue_manager.selected_index = self
            .queue_manager
            .selected_index
            .min(self.prompt_queue.len().saturating_sub(1));
        self.mode = AppMode::Normal;
        self.overlay_kind = None;
    }

    pub fn sync_queue_selection(&mut self) {
        if self.prompt_queue.is_empty() {
            self.queue_manager.selected_index = 0;
            self.queue_paused = false;
            return;
        }

        self.queue_manager.selected_index = self
            .queue_manager
            .selected_index
            .min(self.prompt_queue.len() - 1);
    }

    pub fn open_timeline(&mut self) {
        // render timeline entries as InfoPopup
        let mut lines = vec!["**Agent Timeline**".to_string()];
        if self.timeline_entries.is_empty() {
            lines.push("(no entries yet)".to_string());
        } else {
            for entry in self.timeline_entries.iter().rev().take(50) {
                let kind = match entry.kind {
                    TimelineEntryKind::Phase => "phase",
                    TimelineEntryKind::ToolCall => "tool",
                    TimelineEntryKind::ToolResult => "result",
                    TimelineEntryKind::Permission => "review",
                    TimelineEntryKind::Diff => "diff",
                    TimelineEntryKind::Cost => "cost",
                    TimelineEntryKind::Note => "note",
                    TimelineEntryKind::Checkpoint => "cp",
                };
                let cp_marker = match &entry.checkpoint_id {
                    Some(id) => {
                        let short = if id.len() > 8 { &id[..8] } else { id };
                        format!(" [cp:{short}]")
                    }
                    None => String::new(),
                };
                lines.push(format!("- [{}] {} \u{2014} {}{}", kind, entry.title, entry.detail, cp_marker));
            }
        }
        self.open_info_popup("Timeline", lines.join("\n"));
    }

    pub fn close_timeline(&mut self) {
        self.close_info_popup();
    }

    pub fn open_transcript_search(&mut self) {
        // render transcript as InfoPopup
        self.transcript_search = TranscriptSearchState::default();
        let items = self.transcript_search_items();
        let mut lines = vec!["**Transcript Search**".to_string()];
        if items.is_empty() {
            lines.push("(no items)".to_string());
        } else {
            for item in items.iter().take(40) {
                lines.push(format!("- [{}] {}", item.label, item.detail.lines().next().unwrap_or("")));
            }
        }
        self.open_info_popup("Transcript", lines.join("\n"));
    }

    pub fn close_transcript_search(&mut self) {
        self.transcript_search = TranscriptSearchState::default();
        self.close_info_popup();
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
                MessageRole::ApprovalRequest { tool_name } => (
                    TranscriptSearchItemKind::Tool,
                    format!("Approval / {tool_name}"),
                ),
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
                    TimelineEntryKind::Checkpoint => "Checkpoint",
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
        self.open_info_popup_with_return(title, content, None);
    }

    pub fn open_info_popup_with_return(
        &mut self,
        title: impl Into<String>,
        content: impl Into<String>,
        return_mode: Option<AppMode>,
    ) {
        self.graph_overlay.active = false; // dismiss graph overlay if active
        self.info_popup_title = title.into();
        self.info_popup_content = content.into();
        self.info_popup_scroll = 0;
        self.info_popup_selected_idx = 0;
        self.info_popup_return_mode = return_mode;
        self.mode = AppMode::Overlay;
        self.overlay_kind = Some(OverlayKind::InfoPopup);
    }

    pub fn close_info_popup(&mut self) {
        self.info_popup_title.clear();
        self.info_popup_content.clear();
        self.info_popup_scroll = 0;
        self.info_popup_selected_idx = 0;
        self.overlay_kind = None;
        self.mode = self
            .info_popup_return_mode
            .take()
            .unwrap_or(AppMode::Normal);
    }

    pub fn open_api_key_editor(&mut self, mut state: ApiKeyEditorState) {
        if !state.fields.is_empty() {
            state.selected_index = state.selected_index.min(state.fields.len() - 1);
            let max_cursor = state.fields[state.selected_index].value.len();
            state.cursor = state.cursor.min(max_cursor);
        }
        self.api_key_editor = Some(state);
        self.mode = AppMode::Overlay;
        self.overlay_kind = Some(OverlayKind::ApiKeyEditor);
    }

    pub fn close_api_key_editor(&mut self) {
        self.api_key_editor = None;
        // don't clobber graph overlay if it's active
        if self.overlay_kind != Some(OverlayKind::GraphOverlay) {
            self.mode = AppMode::Normal;
            self.overlay_kind = None;
        }
    }
    pub fn open_list_selector(&mut self, state: ListSelectorState) {
        self.list_selector = Some(state);
        self.mode = AppMode::Overlay;
        self.overlay_kind = Some(OverlayKind::ListSelector);
    }
    pub fn close_list_selector(&mut self) {
        self.list_selector = None;
        self.mode = AppMode::Normal;
        self.overlay_kind = None;
    }

    pub fn open_onboarding(&mut self, step: usize) {
        self.graph_overlay.active = false;
        self.onboarding_active = true;
        self.onboarding_step = step;
        self.onboarding_total_steps = crate::onboarding::onboarding_step_count();
        self.onboarding_try_now = crate::onboarding::ONBOARDING_STEPS
            .get(step)
            .map(|s| s.try_now.to_string())
            .unwrap_or_default();
        self.mode = AppMode::Overlay;
        self.overlay_kind = Some(OverlayKind::Onboarding);
    }

    pub fn close_onboarding(&mut self) {
        self.onboarding_active = false;
        self.onboarding_step = 0;
        self.onboarding_total_steps = 0;
        self.onboarding_try_now.clear();
        self.overlay_kind = None;
        self.mode = AppMode::Normal;
    }

    pub fn scroll_info_popup_up(&mut self, amount: u16) {
        self.info_popup_scroll = self.info_popup_scroll.saturating_sub(amount);
    }

    pub fn scroll_info_popup_down(&mut self, amount: u16) {
        self.info_popup_scroll = self.info_popup_scroll.saturating_add(amount);
    }
    pub fn move_info_popup_selection(&mut self, down: bool, item_count: usize) {
        if item_count == 0 { return; }
        if down {
            if self.info_popup_selected_idx + 1 < item_count {
                self.info_popup_selected_idx += 1;
            }
        } else {
            self.info_popup_selected_idx = self.info_popup_selected_idx.saturating_sub(1);
        }
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
        self.streaming.request_id_counter += 1;
        format!("req-{}", self.streaming.request_id_counter)
    }

    pub fn start_streaming_message(&mut self) {
        let idx = self.messages.len();
        self.messages.push(ChatMessage::assistant(""));
        self.streaming.message = Some(idx);
        self.streaming.thinking_buffer.clear();
        self.streaming.thinking_active = false;
        self.streaming.current_iteration = 0;
        self.tokens.turn_input_tokens = 0;
        self.tokens.turn_output_tokens = 0;
        self.scroll_offset = 0;
    }

    pub fn append_thinking_chunk(&mut self, chunk: &str) {
        self.streaming.thinking_active = true;
        self.streaming.thinking_buffer.push_str(chunk);
        if self.streaming.message.is_none() {
            self.start_streaming_message();
        }
        let thinking_display = self.format_thinking_display();
        if let Some(idx) = self.streaming.message {
            if let Some(msg) = self.messages.get_mut(idx) {
                msg.content = thinking_display;
            }
        }
        if self.scroll_offset <= 1 {
            self.scroll_offset = 0;
        }
    }

    fn format_thinking_display(&self) -> String {
        if self.streaming.thinking_buffer.is_empty() {
            return String::new();
        }
        // Show a condensed view of thinking, last few lines
        let lines: Vec<&str> = self.streaming.thinking_buffer.lines().collect();
        let display_lines = if lines.len() > 20 {
            let hidden = lines.len() - 20;
            let mut out = vec![format!(
                "💭 Thinking ({} lines, {} hidden):",
                lines.len(),
                hidden
            )];
            out.extend(lines[lines.len() - 20..].iter().map(|s| s.to_string()));
            out
        } else {
            let mut out = vec![format!("💭 Thinking ({} lines):", lines.len())];
            out.extend(lines.iter().map(|s| s.to_string()));
            out
        };
        display_lines.join("\n")
    }

    pub fn append_streaming_chunk(&mut self, chunk: &str) {
        // If we were in thinking mode, transition to response mode
        if self.streaming.thinking_active {
            self.streaming.thinking_active = false;
            let thinking_display = self.format_thinking_display();
            let separator = format!("{thinking_display}\n\n---\n\n");
            if let Some(idx) = self.streaming.message {
                if let Some(msg) = self.messages.get_mut(idx) {
                    msg.content = separator;
                }
            }
        }
        if let Some(idx) = self.streaming.message {
            if let Some(msg) = self.messages.get_mut(idx) {
                msg.content.push_str(chunk);
            }
        }
        if self.scroll_offset <= 1 {
            self.scroll_offset = 0;
        }
    }

    pub fn finalize_streaming(&mut self) {
        if let Some(idx) = self.streaming.message {
            if let Some(msg) = self.messages.get(idx) {
                self.record_assistant_output(&msg.content.clone());
            }
        }
        self.streaming.message = None;
        self.streaming.thinking_active = false;
        self.streaming.active_tool = None;
        self.scroll_offset = 0;
    }

    pub fn set_plan(&mut self, steps: Vec<String>, original_request: String) {
        self.set_plan_review(
            steps,
            original_request,
            String::new(),
            String::new(),
            false,
            false,
        );
    }

    pub fn set_plan_review(
        &mut self,
        steps: Vec<String>,
        original_request: String,
        summary: String,
        prompt_id: String,
        is_execution_gate: bool,
        read_only: bool,
    ) {
        self.plan.steps = steps
            .into_iter()
            .map(|s| PlanStep {
                description: s,
                status: PlanStepStatus::Pending,
            })
            .collect();
        self.plan.current_step = 0;
        self.plan.original_request = original_request;
        self.plan.summary = summary;
        self.plan.prompt_id = prompt_id;
        self.plan.is_execution_gate = is_execution_gate;
        self.plan.review_read_only = read_only;
        self.mode = AppMode::InlineApproval;
    }

    pub fn advance_plan_step(&mut self) {
        if self.plan.current_step < self.plan.steps.len() {
            self.plan.steps[self.plan.current_step].status = PlanStepStatus::Done;
            self.plan.current_step += 1;
        }
    }

    pub fn current_plan_step_description(&self) -> Option<&str> {
        self.plan.steps
            .get(self.plan.current_step)
            .map(|s| s.description.as_str())
    }

    pub fn clear_plan(&mut self) {
        self.plan.steps.clear();
        self.plan.current_step = 0;
        self.plan.original_request.clear();
        self.plan.summary.clear();
        self.plan.prompt_id.clear();
        self.plan.is_execution_gate = false;
        self.plan.review_read_only = false;
    }

    pub fn push_suggestion(&mut self, sender: String, text: String) {
        self.pair.suggestions.push_back(Suggestion {
            sender,
            text,
            received_at: Instant::now(),
        });
        while self.pair.suggestions.len() > SUGGESTION_MAX {
            self.pair.suggestions.pop_front();
        }
    }

    pub fn clear_old_suggestions(&mut self) {
        let now = Instant::now();
        while self
            .pair.suggestions
            .front()
            .is_some_and(|s| now.duration_since(s.received_at) > SUGGESTION_TTL)
        {
            self.pair.suggestions.pop_front();
        }
    }

    pub fn latest_suggestion(&self) -> Option<&Suggestion> {
        self.pair.suggestions
            .back()
            .filter(|s| s.received_at.elapsed() < SUGGESTION_HINT_TTL)
    }

    pub fn reset_pair_state(&mut self) {
        self.pair.mode_active = false;
        self.pair.short_code.clear();
        self.pair.invite_code.clear();
        self.pair.is_host = false;
        self.pair.connected_users.clear();
        self.pair.suggestions.clear();
        self.multiplayer.agenda.clear();
        self.multiplayer.agenda_open_count = 0;
        self.multiplayer.agenda_total_count = 0;
        self.multiplayer.ui_role.clear();
        self.multiplayer.mode.clear();
        self.multiplayer.connection_id.clear();
        self.multiplayer.display_name.clear();
        self.multiplayer.approval_state.clear();
        self.multiplayer.hand_raised = false;
        self.multiplayer.queue_position = 0;
        self.multiplayer.remote_invite.clear();
    }

    pub fn can_control_multiplayer_reviews(&self) -> bool {
        self.multiplayer.enabled
            && self.multiplayer.ui_role == "driver"
            && self.multiplayer.approval_state != "pending"
    }

    pub fn update_agenda_from_summary(
        &mut self,
        summary: &serde_json::Map<String, serde_json::Value>,
    ) {
        self.multiplayer.agenda = summary
            .get("openItems")
            .and_then(|value| value.as_array())
            .map(|items| {
                items
                    .iter()
                    .map(|item| CollaborationAgendaItem {
                        item_id: item
                            .get("id")
                            .and_then(|value| value.as_str())
                            .unwrap_or("")
                            .to_string(),
                        text: item
                            .get("text")
                            .and_then(|value| value.as_str())
                            .unwrap_or("")
                            .to_string(),
                        author: item
                            .get("author")
                            .and_then(|value| value.as_str())
                            .unwrap_or("")
                            .to_string(),
                        resolved: item
                            .get("resolved")
                            .and_then(|value| value.as_bool())
                            .unwrap_or(false),
                    })
                    .collect()
            })
            .unwrap_or_default();
        self.multiplayer.agenda_open_count = summary
            .get("open")
            .and_then(|value| value.as_u64())
            .unwrap_or(0);
        self.multiplayer.agenda_total_count = summary
            .get("total")
            .and_then(|value| value.as_u64())
            .unwrap_or(0);
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
            self.provider.name,
            self.provider.model,
            duration,
            self.session_requests,
            self.input_chars,
            self.input_tokens_estimate,
            self.output_chars,
            self.output_tokens_estimate
        )
    }
}

#[derive(Debug, Clone)]
struct AtPathTokenMatch {
    query: String,
    token_start: usize,
    token_end: usize,
    quoted: bool,
    quote_char: char,
}

fn build_at_path_completion_state(app: &App) -> Option<AtPathCompletionState> {
    let token = detect_at_path_token(&app.input_buffer, app.input_cursor)?;
    Some(AtPathCompletionState {
        active: true,
        query: token.query.clone(),
        token_start: token.token_start,
        token_end: token.token_end,
        selected_index: 0,
        quoted: token.quoted,
        quote_char: token.quote_char,
        items: build_at_path_completion_items(app, &token.query, 8),
    })
}

fn detect_at_path_token(buffer: &str, cursor: usize) -> Option<AtPathTokenMatch> {
    if buffer.is_empty() || cursor > buffer.len() || !buffer.is_char_boundary(cursor) {
        return None;
    }

    let before_cursor = &buffer[..cursor];
    let at_index = before_cursor.rfind('@')?;
    if !is_reference_boundary(buffer[..at_index].chars().last()) {
        return None;
    }

    let after_at = &buffer[at_index + 1..];
    if after_at.is_empty() {
        return Some(AtPathTokenMatch {
            query: String::new(),
            token_start: at_index,
            token_end: cursor,
            quoted: false,
            quote_char: '"',
        });
    }

    let first_after = after_at.chars().next()?;
    if first_after.is_whitespace() {
        return None;
    }

    if first_after == '"' || first_after == '\'' {
        let content_start = at_index + 1 + first_after.len_utf8();
        if cursor < content_start {
            return None;
        }

        let closing_index = buffer[content_start..]
            .find(first_after)
            .map(|relative| content_start + relative + first_after.len_utf8())
            .unwrap_or(cursor);
        if cursor > closing_index {
            return None;
        }

        return Some(AtPathTokenMatch {
            query: buffer[content_start..cursor].to_string(),
            token_start: at_index,
            token_end: closing_index,
            quoted: true,
            quote_char: first_after,
        });
    }

    let token_end = find_unquoted_reference_end(buffer, at_index + 1);
    if cursor > token_end {
        return None;
    }

    Some(AtPathTokenMatch {
        query: buffer[at_index + 1..cursor].to_string(),
        token_start: at_index,
        token_end,
        quoted: false,
        quote_char: '"',
    })
}

fn find_unquoted_reference_end(buffer: &str, start: usize) -> usize {
    for (offset, ch) in buffer[start..].char_indices() {
        if !is_unquoted_reference_char(ch) {
            return start + offset;
        }
    }
    buffer.len()
}

fn build_at_path_completion_items(
    app: &App,
    query: &str,
    limit: usize,
) -> Vec<AtPathCompletionItem> {
    if limit == 0 || app.cwd.trim().is_empty() {
        return Vec::new();
    }

    let root = Path::new(&app.cwd);
    if !root.exists() || !root.is_dir() {
        return Vec::new();
    }

    let normalized_query = normalize_reference_query(query);
    let mut scored: Vec<(usize, usize, AtPathCompletionItem)> = Vec::new();
    let mut seen = HashSet::new();

    let mut push_candidate =
        |path: String,
         detail: &str,
         score: usize,
         scored: &mut Vec<(usize, usize, AtPathCompletionItem)>| {
            let normalized_path = path.trim().trim_start_matches("./").to_string();
            if normalized_path.is_empty() || !seen.insert(normalized_path.clone()) {
                return;
            }
            scored.push((
                score,
                normalized_path.len(),
                AtPathCompletionItem {
                    path: normalized_path,
                    detail: detail.to_string(),
                },
            ));
        };

    if normalized_query.is_empty() {
        for path in &app.pinned_context_files {
            push_candidate(path.clone(), "pinned", 0, &mut scored);
        }
        for path in app.recent_edited_files.iter() {
            if let Some(relative) = normalize_candidate_path(root, path) {
                push_candidate(relative, "recent", 1, &mut scored);
            }
        }
    }

    let mut queue = VecDeque::from([root.to_path_buf()]);
    while let Some(dir) = queue.pop_front() {
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };

        let mut sorted_entries = entries.flatten().collect::<Vec<_>>();
        sorted_entries.sort_by_key(|entry| entry.file_name().to_string_lossy().to_string());

        for entry in sorted_entries {
            let path = entry.path();
            if path.is_dir() {
                let name = entry.file_name().to_string_lossy().to_string();
                if should_skip_dir(&name) {
                    continue;
                }
                queue.push_back(path);
                continue;
            }

            if !path.is_file() {
                continue;
            }

            let relative = relative_display_path(root, &path);
            let Some(score) = score_path_candidate(&relative, &normalized_query) else {
                continue;
            };
            push_candidate(relative, "file", score + 2, &mut scored);
            if scored.len() >= limit.saturating_mul(6) {
                break;
            }
        }

        if scored.len() >= limit.saturating_mul(6) {
            break;
        }
    }

    scored.sort_by(|left, right| {
        left.0
            .cmp(&right.0)
            .then(left.1.cmp(&right.1))
            .then(left.2.path.cmp(&right.2.path))
    });
    scored
        .into_iter()
        .take(limit)
        .map(|(_, _, item)| item)
        .collect()
}

fn normalize_candidate_path(root: &Path, value: &str) -> Option<String> {
    let path = PathBuf::from(value);
    let candidate = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    if !candidate.is_file() {
        return None;
    }
    Some(relative_display_path(root, &candidate))
}

fn normalize_reference_query(query: &str) -> String {
    query
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .trim_start_matches("./")
        .to_ascii_lowercase()
}

fn relative_display_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .ok()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|| path.to_string_lossy().to_string())
}

fn score_path_candidate(path: &str, normalized_query: &str) -> Option<usize> {
    if normalized_query.is_empty() {
        return Some(0);
    }

    let path_lower = path.to_ascii_lowercase();
    let file_name = path.rsplit('/').next().unwrap_or(path).to_ascii_lowercase();

    if path_lower == normalized_query {
        Some(0)
    } else if path_lower.starts_with(normalized_query) {
        Some(1)
    } else if path_lower.contains(&format!("/{normalized_query}")) {
        Some(2)
    } else if file_name.starts_with(normalized_query) {
        Some(3)
    } else if path_lower.contains(normalized_query) {
        Some(4)
    } else {
        None
    }
}

fn render_at_path_token(path: &str, quoted: bool, quote_char: char) -> String {
    if quoted || path.contains(char::is_whitespace) {
        let quote = if quote_char == '\'' { '\'' } else { '"' };
        format!("@{quote}{path}{quote}")
    } else {
        format!("@{path}")
    }
}

fn is_reference_boundary(previous: Option<char>) -> bool {
    match previous {
        None => true,
        Some(ch) => ch.is_whitespace() || matches!(ch, '(' | '[' | '{' | ',' | ';' | ':' | '<'),
    }
}

fn is_unquoted_reference_char(ch: char) -> bool {
    !ch.is_whitespace()
        && !matches!(
            ch,
            '"' | '\'' | '`' | ',' | ';' | ':' | ')' | ']' | '}' | '(' | '[' | '{'
        )
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
        AppMode, MutationReviewState, ProviderEntry, ThemeMode,
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
    fn provider_select_defaults_to_active_provider_and_model() {
        let mut app = super::App::new();
        app.provider.name = "openai".to_string();
        app.provider.model = crate::provider_catalog::default_model("openai").to_string();
        app.provider.list = vec![
            ProviderEntry {
                name: "anthropic".to_string(),
                available: true,
                ready: true,
                status_label: "API key configured".to_string(),
                models: vec!["claude-sonnet".to_string()],
            },
            ProviderEntry {
                name: "openai".to_string(),
                available: true,
                ready: true,
                status_label: "API key configured".to_string(),
                models: vec![
                    "gpt-5-mini".to_string(),
                    crate::provider_catalog::default_model("openai").to_string(),
                ],
            },
        ];

        app.open_provider_select();

        assert_eq!(app.provider.select_idx, 1);
        assert_eq!(app.selected_provider_model_index(), Some(1));
        assert_eq!(
            app.selected_provider_model().as_deref(),
            Some(crate::provider_catalog::default_model("openai"))
        );
    }

    #[test]
    fn opening_mutation_review_enters_mutation_review_mode() {
        let mut app = super::App::new();

        app.open_mutation_review(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "write_file".to_string(),
            operation: "write_file".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.txt".to_string()],
            diff: "@@ -0,0 +1 @@\n+hello".to_string(),
            checkpoint_id: Some("cp-1".to_string()),
            changed: Some(true),
            message: "Preview write".to_string(),
            selected_path_index: 0,
            chunks: Vec::new(),
            selected_chunk_index: 0,
        });

        assert_eq!(app.mode, AppMode::InlineApproval);
    }
}
