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
    // Command input mode (slash commands)
    Command,
    ProviderSelect,
    PermissionPrompt,
    Quitting,
}

/// Spinner frames for the thinking indicator.
pub const SPINNER_FRAMES: &[&str] = &["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

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

    // ── Permission prompt state ───
    pub permission_message: String,
    pub permission_answer: Option<bool>,

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
            streaming_enabled: true,
            version: "0.4.0".into(),
            waiting: false,
            spinner_tick: 0,
            wait_start: None,
            command_history: VecDeque::with_capacity(100),
            history_index: None,
            permission_message: String::new(),
            permission_answer: None,
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
        }
    }
}

impl App {
    pub fn new() -> Self {
        Self::default()
    }

    fn welcome_text(&self) -> String {
        let logo = r#" ____   ___   ___  ____        ____ _     ___
|  _ \ / _ \ / _ \|  _ \      / ___| |   |_ _|
| |_) | | | | | | | |_) |    | |   | |    | |
|  __/| |_| | |_| |  _ <     | |___| |___ | |
|_|    \___/ \___/|_| \_\     \____|_____|___|"#;
        format!(
            "{logo}\n\n\
            poor-cli v{version}  •  {provider}/{model}\n\
            AI-powered coding assistant in your terminal\n\n\
            Commands:\n  \
            /help         Show all commands\n  \
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
    }

    /// Retroactively update the welcome message after init completes.
    pub fn update_welcome(&mut self) {
        let text = self.welcome_text();
        if let Some(msg) = self.messages.first_mut() {
            if matches!(msg.role, MessageRole::System) {
                msg.content = text;
            }
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

        // Save to history
        if !text.is_empty() {
            self.command_history.push_front(text.clone());
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

    /// Clear status if it's older than 3 seconds.
    pub fn clear_old_status(&mut self) {
        if let Some((_, when)) = &self.status_message {
            if when.elapsed().as_secs() > 3 {
                self.status_message = None;
            }
        }
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
