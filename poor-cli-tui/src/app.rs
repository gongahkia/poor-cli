/// Application state machine for the poor-cli TUI.
use std::collections::VecDeque;
use std::time::Instant;

// ── Message model ────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum MessageRole {
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

// ── Application state ────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum AppMode {
    Normal,
    Command,
    ProviderSelect,
    InfoPopup,
    PermissionPrompt,
    PlanReview,
    CompactSelect,
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

pub const DOLLAR_FRAMES: &[&str] = &[
    // front
    r#"    ┌─┐
   ┌┘$└┐
   │ $ │
   │ $ │
   └┐$┌┘
    └─┘ "#,
    // tilt right
    r#"     ╲
    ╱ $ ╲
   ╱  $  ╲
   ╲  $  ╱
    ╲ $ ╱
     ╱   "#,
    // edge
    r#"      │
      │
      │
      │
      │
      │"#,
    // tilt left
    r#"   ╱
  ╲ $ ╱
   ╲$  ╱
   ╱  $╱
  ╱ $ ╲
   ╲    "#,
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

    // ── Command history ───
    pub command_history: VecDeque<String>,
    pub history_index: Option<usize>,
    pub command_match_index: usize,

    // ── Permission prompt state ───
    pub permission_message: String,
    pub permission_answer: Option<bool>,
    pub permission_prompt_id: String,

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
    pub autopilot_enabled: bool,
    pub last_command_output: Option<String>,
    pub execution_profile: String,
    pub context_budget_tokens: usize,
    pub context_budget_files: Vec<String>,
    pub context_budget_estimated_tokens: usize,
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

    // ── Real token tracking (from server) ───
    pub turn_input_tokens: u64,
    pub turn_output_tokens: u64,
    pub cumulative_input_tokens: u64,
    pub cumulative_output_tokens: u64,
    pub response_mode: ResponseMode,
    pub theme_mode: ThemeMode,
    pub compact_select_idx: usize,
    pub welcome_anim_tick: usize,
    pub welcome_anim_active: bool,
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
            command_history: VecDeque::with_capacity(100),
            history_index: None,
            command_match_index: 0,
            permission_message: String::new(),
            permission_answer: None,
            permission_prompt_id: String::new(),
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
            autopilot_enabled: false,
            last_command_output: None,
            execution_profile: "safe".to_string(),
            context_budget_tokens: 6000,
            context_budget_files: Vec::new(),
            context_budget_estimated_tokens: 0,
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
            turn_input_tokens: 0,
            turn_output_tokens: 0,
            cumulative_input_tokens: 0,
            cumulative_output_tokens: 0,
            response_mode: ResponseMode::Rich,
            theme_mode: ThemeMode::Dark,
            compact_select_idx: 0,
            welcome_anim_tick: 0,
            welcome_anim_active: true,
        }
    }
}

impl App {
    pub fn new() -> Self {
        Self::default()
    }

    fn welcome_text(&self) -> String {
        let dollar = DOLLAR_FRAMES[self.welcome_anim_tick % DOLLAR_FRAMES.len()];
        let logo = r#" ____   ___   ___  ____        ____ _     ___
|  _ \ / _ \ / _ \|  _ \      / ___| |   |_ _|
| |_) | | | | | | | |_) |    | |   | |    | |
|  __/| |_| | |_| |  _ <     | |___| |___ | |
|_|    \___/ \___/|_| \_\     \____|_____|___|"#;
        format!(
            "{dollar}\n\n{logo}\n\n\
            poor-cli v{version}  •  {provider}/{model}\n\
            AI-powered coding assistant in your terminal\n\n\
            Commands:\n  \
            /help         Show all commands\n  \
            /onboarding   Interactive command walkthrough\n  \
            /switch       Switch AI provider\n  \
            /providers    List all providers\n  \
            /quit         Exit\n\n\
            Tip: History automatically persists across sessions",
            version = self.version,
            provider = self.provider_name,
            model = self.model_name,
        )
    }

    /// Add a welcome message on startup.
    pub fn add_welcome(&mut self) {
        self.messages.push(ChatMessage::system(self.welcome_text()));
        self.scroll_offset = 0;
    }

    /// Retroactively update the welcome message after init completes.
    pub fn update_welcome(&mut self) {
        let text = self.welcome_text();
        if let Some(msg) = self.messages.first_mut() {
            if matches!(msg.role, MessageRole::System) {
                msg.content = text;
            }
        }
        self.scroll_offset = 0;
    }

    /// Push a message and auto-scroll to bottom.
    pub fn push_message(&mut self, msg: ChatMessage) {
        if matches!(msg.role, MessageRole::User) {
            self.welcome_anim_active = false;
        }
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

    pub fn tick_welcome_anim(&mut self) {
        if self.welcome_anim_active && self.messages.len() <= 1 {
            self.welcome_anim_tick = (self.welcome_anim_tick + 1) % DOLLAR_FRAMES.len();
            self.update_welcome();
        }
    }

    /// Get the current spinner frame.
    pub fn spinner_frame(&self) -> &str {
        SPINNER_FRAMES[self.spinner_tick % SPINNER_FRAMES.len()]
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
        self.plan_steps = steps
            .into_iter()
            .map(|s| PlanStep {
                description: s,
                status: PlanStepStatus::Pending,
            })
            .collect();
        self.plan_current_step = 0;
        self.plan_original_request = original_request;
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
    use super::ThemeMode;

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
}
