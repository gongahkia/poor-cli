use super::*;

pub(crate) fn handle_submit(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &session::BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
    text: &str,
) -> bool {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return false;
    }

    // auto-queue non-slash input while AI is working
    if app.waiting && !trimmed.starts_with('/') && !trimmed.starts_with('!') {
        app.prompt_queue.push_back(QueuedPrompt::user(trimmed));
        app.sync_queue_selection();
        app.set_status(format!(
            "Queued prompt ({} in queue)",
            app.prompt_queue.len()
        ));
        return false;
    }

    let submit_kind = if trimmed.starts_with('/') {
        "slash"
    } else if trimmed.starts_with('!') {
        "bang"
    } else {
        "chat"
    };
    session::write_session_log(
        launch.session_log.as_ref(),
        &format!("submit_dispatch kind={submit_kind} chars={}", trimmed.len()),
    );

    // join wizard is now handled via AppMode::JoinWizard popup (see input.rs)

    if let Some(prompt_name) = app.pending_prompt_save_name.clone() {
        if !trimmed.starts_with('/') {
            app.pending_prompt_save_name = None;
            match save_prompt(app, &prompt_name, trimmed) {
                Ok(path) => app.set_status(format!("Saved prompt: {}", path.display())),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        app.pending_prompt_save_name = None;
        app.set_status("Prompt capture cancelled");
    }

    if trimmed.starts_with('/') {
        let slash_command = trimmed
            .split_whitespace()
            .next()
            .unwrap_or("/unknown")
            .trim_start_matches('/');
        session::write_session_log(
            launch.session_log.as_ref(),
            &format!("slash_command_dispatch command={slash_command}"),
        );
        return commands::handle_slash_command(
            app,
            tx,
            rpc_cmd_tx,
            launch,
            cancel_token,
            watch_state,
            qa_watch_state,
            trimmed,
        );
    }

    if let Some(bang_input) = parse_bang_command(trimmed) {
        match rpc_execute_command_with_timeout_blocking(
            rpc_cmd_tx,
            &bang_input.command,
            Some(BANG_COMMAND_TIMEOUT_SECS),
            BANG_COMMAND_RESPONSE_TIMEOUT_SECS,
        ) {
            Ok(output) => {
                app.last_command_output = Some(output.clone());
                let command_preview = truncate_block(&output, 1200);
                app.push_message(ChatMessage::system(format!(
                    "**Bash command executed:** `{}`\n```text\n{command_preview}\n```",
                    bang_input.command
                )));

                let prompt_from_bash = build_bang_command_prompt(
                    &bang_input.command,
                    &output,
                    bang_input.question.as_deref(),
                );
                let backend_message = with_pending_images(app, &prompt_from_bash);
                let backend_message =
                    apply_response_mode_to_user_input(app.response_mode, &backend_message);
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    backend_message,
                    trimmed.to_string(),
                    launch.session_log.as_ref(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Bash command failed: {e}\nTip: use `!<command> | <question>` to ask about command output, or `/run <command>` for raw output only."
            ))),
        }
        return false;
    }

    refresh_context_budget_state(app);
    let prepared_request = match prepare_context_request(app, trimmed) {
        Ok(request) => request,
        Err(error_message) => {
            app.push_message(ChatMessage::error(error_message));
            return false;
        }
    };
    let backend_message = with_pending_images(app, &prepared_request.message);
    let backend_message = apply_response_mode_to_user_input(app.response_mode, &backend_message);
    send_chat_request_with_context(
        app,
        tx,
        rpc_cmd_tx,
        cancel_token,
        backend_message,
        prepared_request.explicit_files,
        prepared_request.pinned_files,
        trimmed.to_string(),
        launch.session_log.as_ref(),
    );
    false
}

pub(crate) fn send_chat_request(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    backend_message: String,
    display_message: String,
    session_log: Option<&session::SessionLogWriter>,
) {
    send_chat_request_with_context(
        app,
        tx,
        rpc_cmd_tx,
        cancel_token,
        backend_message,
        Vec::new(),
        Vec::new(),
        display_message,
        session_log,
    );
}

pub(crate) fn send_chat_request_with_context(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    backend_message: String,
    explicit_context_files: Vec<String>,
    pinned_context_files: Vec<String>,
    display_message: String,
    session_log: Option<&session::SessionLogWriter>,
) {
    const STREAM_REPLY_TIMEOUT_SECS: u64 = 130;

    let display_kind = session::chat_display_kind(&display_message);
    let display_char_count = display_message.chars().count();
    let backend_char_count = backend_message.chars().count();

    cancel_token.store(false, Ordering::SeqCst);
    app.remember_recent_prompt(&display_message);
    app.record_user_input(&display_message);
    app.push_message(ChatMessage::user(display_message));
    app.start_waiting();
    app.tokens.turn_input_tokens = 0;
    app.tokens.turn_output_tokens = 0;

    // use streaming endpoint — notifications arrive via the notification channel
    let request_id = app.next_request_id();
    app.streaming.active_request_id = request_id.clone();
    app.streaming.active_request_started_at = Some(std::time::Instant::now());
    session::write_session_log(
        session_log,
        &format!(
            "chat_request_start request_id={} kind={} display_chars={} backend_chars={}",
            request_id, display_kind, display_char_count, backend_char_count
        ),
    );
    let tx2 = tx.clone();
    let cancel = cancel_token.clone();
    let request_id_for_thread = request_id.clone();
    let log_ctx = session_log.cloned();
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    if rpc_cmd_tx
        .send(RpcCommand::ChatStreaming {
            message: backend_message,
            request_id,
            context_files: explicit_context_files,
            pinned_context_files,
            context_budget_tokens: Some(app.context_budget_tokens),
            reply: reply_tx,
        })
        .is_err()
    {
        app.stop_waiting();
        app.streaming.active_request_id.clear();
        app.streaming.active_request_started_at = None;
        session::write_session_log(
            session_log,
            "chat_request_send_error reason=rpc_worker_unavailable",
        );
        app.push_message(ChatMessage::error(
            "Failed to send request: RPC worker unavailable",
        ));
        return;
    }

    thread::spawn(move || {
        match reply_rx.recv_timeout(Duration::from_secs(STREAM_REPLY_TIMEOUT_SECS)) {
            Ok(Ok(_content)) => {
                // streaming already delivered chunks via notifications.
                // the final result is ignored since finalize_streaming handles it.
                session::write_session_log(
                    log_ctx.as_ref(),
                    &format!(
                        "chat_request_rpc_result request_id={} status=ok",
                        request_id_for_thread
                    ),
                );
            }
            Ok(Err(e)) => {
                session::write_session_log(
                    log_ctx.as_ref(),
                    &format!(
                        "chat_request_rpc_result request_id={} status=error error={}",
                        request_id_for_thread,
                        truncate_line(&e.replace('\n', " "), 180)
                    ),
                );
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error { message: e });
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                session::write_session_log(
                    log_ctx.as_ref(),
                    &format!(
                        "chat_request_rpc_result request_id={} status=timeout",
                        request_id_for_thread
                    ),
                );
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "Timed out waiting for backend response".into(),
                    });
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                session::write_session_log(
                    log_ctx.as_ref(),
                    &format!(
                        "chat_request_rpc_result request_id={} status=disconnected",
                        request_id_for_thread
                    ),
                );
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "RPC worker reply channel disconnected".into(),
                    });
                }
            }
        }
    });
}

pub(crate) fn dispatch_next_queued_prompt(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    session_log: Option<&session::SessionLogWriter>,
) {
    if app.waiting || app.prompt_queue.is_empty() || app.queue_paused || !app.plan.steps.is_empty()
    {
        return;
    }
    if let Some(next_prompt) = app.prompt_queue.pop_front() {
        app.sync_queue_selection();
        let remaining = app.prompt_queue.len();
        app.push_message(ChatMessage::system(format!(
            "[queue] auto-sending next {} prompt ({remaining} remaining)",
            next_prompt.source
        )));
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            next_prompt.backend,
            next_prompt.display,
            session_log,
        );
    }
}

const MAX_CONTEXT_FILES_PER_REQUEST: usize = 12;

pub(crate) fn prepare_context_request(app: &mut App, message: &str) -> Result<session::PreparedContextRequest, String> {
    let inline_specs = extract_at_references(message)?;

    let mut seen_paths = HashSet::<String>::new();
    let mut unresolved_refs = Vec::<String>::new();
    let mut ambiguous_refs = Vec::<String>::new();
    let mut explicit_paths = Vec::<PathBuf>::new();

    for spec in &inline_specs {
        let matches = resolve_context_spec(app, spec);
        if matches.is_empty() {
            unresolved_refs.push(spec.clone());
            continue;
        }

        if matches.len() > 1 {
            let preview = matches
                .iter()
                .take(3)
                .map(|path| format!("`{}`", display_project_path(app, path)))
                .collect::<Vec<_>>()
                .join(", ");
            ambiguous_refs.push(format!("`{spec}` -> {preview}"));
            continue;
        }

        let path = matches[0].clone();
        let key = path.to_string_lossy().to_string();
        if seen_paths.insert(key) {
            explicit_paths.push(path);
        }
    }

    if !unresolved_refs.is_empty() || !ambiguous_refs.is_empty() {
        let mut lines =
            vec!["Cannot send message because one or more `@` references are invalid.".to_string()];
        if !unresolved_refs.is_empty() {
            lines.push(format!(
                "Unresolved: {}",
                unresolved_refs
                    .iter()
                    .map(|spec| format!("`@{spec}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        if !ambiguous_refs.is_empty() {
            lines.push(format!("Ambiguous: {}", ambiguous_refs.join(" ; ")));
            lines.push(
                "Use a more specific path (or quote it) so each `@` maps to exactly one file."
                    .to_string(),
            );
        }
        lines
            .push("Tip: paths with spaces must be quoted like `@\"docs/My File.md\"`.".to_string());
        return Err(lines.join("\n"));
    }

    let mut pinned_paths = Vec::<PathBuf>::new();
    if !app.pinned_context_files.is_empty() {
        let remaining = MAX_CONTEXT_FILES_PER_REQUEST.saturating_sub(explicit_paths.len());
        let pinned_resolved = resolve_context_specs(app, &app.pinned_context_files, remaining);
        for path in pinned_resolved {
            let key = path.to_string_lossy().to_string();
            if seen_paths.insert(key) {
                pinned_paths.push(path);
            }
        }
    }

    if explicit_paths.is_empty() && pinned_paths.is_empty() {
        return Ok(session::PreparedContextRequest {
            message: message.to_string(),
            explicit_files: Vec::new(),
            pinned_files: Vec::new(),
        });
    }

    let attached = explicit_paths
        .iter()
        .chain(pinned_paths.iter())
        .map(|path| display_project_path(app, path))
        .collect::<Vec<_>>();
    let attached_summary = attached
        .iter()
        .take(3)
        .cloned()
        .collect::<Vec<_>>()
        .join(", ");
    let extra = attached.len().saturating_sub(3);
    let source_label = if !inline_specs.is_empty() && !pinned_paths.is_empty() {
        "@ references and pinned files"
    } else if !inline_specs.is_empty() {
        "@ references"
    } else {
        "pinned files"
    };
    if extra > 0 {
        app.set_status(format!(
            "Attached {} {} ({attached_summary}, +{extra} more)",
            attached.len(),
            source_label
        ));
    } else {
        app.set_status(format!(
            "Attached {} {} ({attached_summary})",
            attached.len(),
            source_label
        ));
    }

    Ok(session::PreparedContextRequest {
        message: message.to_string(),
        explicit_files: explicit_paths
            .into_iter()
            .map(|path| path.to_string_lossy().to_string())
            .collect(),
        pinned_files: pinned_paths
            .into_iter()
            .map(|path| path.to_string_lossy().to_string())
            .collect(),
    })
}

pub(crate) fn extract_at_references(message: &str) -> Result<Vec<String>, String> {
    let mut seen = HashSet::new();
    let mut refs = Vec::new();
    let mut parse_errors = Vec::new();
    let chars: Vec<char> = message.chars().collect();
    let mut idx = 0usize;

    while idx < chars.len() {
        if chars[idx] != '@' {
            idx += 1;
            continue;
        }

        if !is_reference_boundary(idx.checked_sub(1).and_then(|i| chars.get(i).copied())) {
            idx += 1;
            continue;
        }

        let next_idx = idx + 1;
        if next_idx >= chars.len() || chars[next_idx].is_whitespace() {
            idx += 1;
            continue;
        }

        if chars[next_idx] == '"' || chars[next_idx] == '\'' {
            let quote = chars[next_idx];
            let mut end_idx = next_idx + 1;
            while end_idx < chars.len() && chars[end_idx] != quote {
                end_idx += 1;
            }
            if end_idx >= chars.len() {
                parse_errors.push("unterminated quoted @ reference".to_string());
                break;
            }

            let spec = chars[next_idx + 1..end_idx]
                .iter()
                .collect::<String>()
                .trim()
                .to_string();
            if spec.is_empty() {
                parse_errors.push("empty quoted @ reference".to_string());
            } else if seen.insert(spec.clone()) {
                refs.push(spec);
            }

            idx = end_idx + 1;
            continue;
        }

        let mut end_idx = next_idx;
        while end_idx < chars.len() && is_unquoted_reference_char(chars[end_idx]) {
            end_idx += 1;
        }

        let spec = chars[next_idx..end_idx]
            .iter()
            .collect::<String>()
            .trim()
            .to_string();
        if !spec.is_empty() && seen.insert(spec.clone()) {
            refs.push(spec);
        }

        idx = if end_idx > idx { end_idx } else { idx + 1 };
    }

    if parse_errors.is_empty() {
        Ok(refs)
    } else {
        Err(format!(
            "Invalid @ reference syntax: {}",
            parse_errors.join("; ")
        ))
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

pub(crate) fn resolve_context_specs(app: &App, specs: &[String], limit: usize) -> Vec<PathBuf> {
    if limit == 0 {
        return Vec::new();
    }
    let mut out = Vec::new();
    let mut seen = HashSet::new();

    for spec in specs {
        for path in resolve_context_spec(app, spec) {
            let key = path.to_string_lossy().to_string();
            if seen.insert(key) {
                out.push(path);
            }
            if out.len() >= limit {
                return out;
            }
        }
    }

    out
}

pub(crate) fn resolve_context_spec(app: &App, spec: &str) -> Vec<PathBuf> {
    let cwd = Path::new(&app.cwd);
    let raw_path = PathBuf::from(spec);
    let candidate = if raw_path.is_absolute() {
        raw_path
    } else {
        cwd.join(raw_path)
    };

    if candidate.is_file() {
        return vec![candidate];
    }

    if candidate.is_dir() {
        return collect_directory_files(&candidate, 8);
    }

    find_suffix_matches(cwd, spec, 5)
}

pub(crate) fn collect_directory_files(root: &Path, limit: usize) -> Vec<PathBuf> {
    let mut queue = VecDeque::from([root.to_path_buf()]);
    let mut files = Vec::new();

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

            if path.is_file() {
                files.push(path);
                if files.len() >= limit {
                    return files;
                }
            }
        }
    }

    files
}

pub(crate) fn find_suffix_matches(root: &Path, suffix: &str, limit: usize) -> Vec<PathBuf> {
    let mut queue = VecDeque::from([root.to_path_buf()]);
    let mut matches = Vec::new();
    let normalized = suffix.trim_start_matches("./");

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

            let rel = path
                .strip_prefix(root)
                .ok()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| path.to_string_lossy().to_string());
            if rel == normalized || rel.ends_with(normalized) {
                matches.push(path);
                if matches.len() >= limit {
                    return matches;
                }
            }
        }
    }

    matches
}

pub(crate) fn display_project_path(app: &App, path: &Path) -> String {
    let cwd = Path::new(&app.cwd);
    path.strip_prefix(cwd)
        .ok()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|| path.to_string_lossy().to_string())
}

pub(crate) fn with_pending_images(app: &mut App, message: &str) -> String {
    if app.pending_images.is_empty() {
        return message.to_string();
    }

    let queued = std::mem::take(&mut app.pending_images);
    let attachment_lines = queued
        .iter()
        .map(|p| format!("- {p}"))
        .collect::<Vec<_>>()
        .join("\n");

    format!(
        "{message}\n\nAttached image files (paths):\n{attachment_lines}\n\nUse these images as context when possible."
    )
}

pub(crate) fn apply_response_mode_to_user_input(mode: ResponseMode, user_input: &str) -> String {
    let mode_instruction = match mode {
        ResponseMode::Poor => {
            "Response mode is poor. Keep the answer as short as possible while still correct. \
Use minimal tokens and avoid extra explanation unless explicitly requested."
        }
        ResponseMode::Rich => {
            "Response mode is rich. Prioritize quality, completeness, and clear structure. \
Cover important reasoning and tradeoffs when relevant."
        }
    };

    format!("{mode_instruction}\n\nUser request:\n{user_input}")
}

pub(crate) const BANG_COMMAND_MAX_OUTPUT_CHARS: usize = 16_000;
pub(crate) const BANG_COMMAND_TIMEOUT_SECS: u64 = 120;
pub(crate) const BANG_COMMAND_RESPONSE_TIMEOUT_SECS: u64 = 150;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BangCommandInput {
    pub command: String,
    pub question: Option<String>,
}

pub(crate) fn parse_bang_command(input: &str) -> Option<BangCommandInput> {
    let trimmed = input.trim();
    let payload = trimmed.strip_prefix('!')?.trim();
    if payload.is_empty() {
        None
    } else {
        let (command_raw, question_raw) = if let Some((command, question)) = payload.split_once('|')
        {
            (command.trim(), Some(question.trim()))
        } else {
            (payload, None)
        };

        if command_raw.is_empty() {
            return None;
        }

        let question = question_raw
            .filter(|value| !value.is_empty())
            .map(|value| value.to_string());

        Some(BangCommandInput {
            command: command_raw.to_string(),
            question,
        })
    }
}

pub(crate) fn build_bang_command_prompt(command: &str, output: &str, question: Option<&str>) -> String {
    let content = if output.trim().is_empty() {
        "(command produced no output)"
    } else {
        output
    };

    let mut prompt = format!(
        "I ran a local shell command and want help based on its output.\n\n\
Command: `{command}`\n\n\
Output:\n```text\n{}\n```",
        truncate_block(content, BANG_COMMAND_MAX_OUTPUT_CHARS)
    );

    if let Some(user_question) = question.filter(|value| !value.trim().is_empty()) {
        prompt.push_str(&format!("\n\nUser question: {user_question}"));
    }

    prompt
}

pub(crate) struct OnboardingStep {
    pub title: &'static str,
    pub objective: &'static str,
    pub commands: &'static [&'static str],
    pub try_now: &'static str,
}

pub(crate) const ONBOARDING_STEPS: &[OnboardingStep] = &[
    OnboardingStep {
        title: "Get Oriented",
        objective:
            "Start with visibility into your session and where to find command docs quickly.",
        commands: &[
            "/help",
            "/status",
            "/bootstrap",
            "/profile status",
            "/search <term>",
        ],
        try_now: "/bootstrap",
    },
    OnboardingStep {
        title: "Choose Provider + Model",
        objective: "Inspect your active model, switch when needed, and configure provider auth without leaving the TUI.",
        commands: &["/setup", "/provider", "/providers", "/switch", "/api-key status"],
        try_now: "/setup",
    },
    OnboardingStep {
        title: "Run Local Services",
        objective: "Control local dependencies from the TUI instead of shelling out.",
        commands: &[
            "/service status",
            "/service start <name> <command...>",
            "/service logs <name> [lines]",
            "/ollama start",
        ],
        try_now: "/service status",
    },
    OnboardingStep {
        title: "Run Collaboration Sessions",
        objective: "Start a mob or review room, invite collaborators, and keep the session moving with handoff and agenda commands.",
        commands: &[
            "/collab start mob",
            "/collab join <invite-code>",
            "/collab members",
            "/collab handoff next",
            "/collab agenda add <text>",
        ],
        try_now: "/collab start mob",
    },
    OnboardingStep {
        title: "Daily Coding Workflow",
        objective: "Use these commands for context, review, tests, and quick rollback checkpoints.",
        commands: &[
            "/add <path>",
            "/files",
            "/review [file]",
            "/test <file>",
            "/checkpoint",
            "/rewind [id|last]",
        ],
        try_now: "/files",
    },
];

pub(crate) fn onboarding_step_count() -> usize {
    ONBOARDING_STEPS.len()
}

pub(crate) fn onboarding_navigation_hint() -> &'static str {
    "Navigation: `/onboarding next` • `/onboarding prev` • `/onboarding <step>` • `/onboarding exit`"
}

pub(crate) fn format_onboarding_step(step_index: usize) -> String {
    if ONBOARDING_STEPS.is_empty() {
        return "Onboarding is currently unavailable.".to_string();
    }

    let total = onboarding_step_count();
    let idx = step_index.min(total.saturating_sub(1));
    let step = &ONBOARDING_STEPS[idx];

    let mut lines = vec![
        format!("**Onboarding {}/{}: {}**", idx + 1, total, step.title),
        String::new(),
        step.objective.to_string(),
        String::new(),
        "**Core commands**".to_string(),
    ];

    lines.extend(step.commands.iter().map(|cmd| format!("- `{cmd}`")));
    lines.push(String::new());
    lines.push(format!("Try now: `{}`", step.try_now));

    if idx + 1 == total {
        lines.push(
            "You reached the final step. Run `/onboarding exit` to end this onboarding session."
                .to_string(),
        );
    }

    lines.push(String::new());
    lines.push(onboarding_navigation_hint().to_string());
    lines.join("\n")
}

pub(crate) fn startup_intro_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("startup-onboarding-seen")
}

pub(crate) fn is_startup_first_launch(app: &App) -> bool {
    !startup_intro_state_path(app).exists()
}

pub(crate) fn mark_startup_first_launch_seen(app: &App) -> Result<(), String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root).map_err(|e| format!("Failed to create data directory: {e}"))?;
    fs::write(startup_intro_state_path(app), b"seen\n")
        .map_err(|e| format!("Failed to persist startup onboarding state: {e}"))
}

pub(crate) fn status_view_has_unconfigured_provider(payload: &Value) -> bool {
    payload
        .pointer("/provider/readiness")
        .and_then(|value| value.as_object())
        .map(|entries| {
            entries.values().any(|entry| {
                !entry
                    .get("ready")
                    .and_then(|value| value.as_bool())
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

pub(crate) fn status_view_ready_provider_count(payload: &Value) -> usize {
    payload
        .pointer("/provider/readiness")
        .and_then(|value| value.as_object())
        .map(|entries| {
            entries
                .values()
                .filter(|entry| {
                    entry
                        .get("ready")
                        .and_then(|value| value.as_bool())
                        .unwrap_or(false)
                })
                .count()
        })
        .unwrap_or(0)
}

pub(crate) fn start_startup_onboarding_intro(app: &mut App, popup: bool) {
    app.onboarding_active = true;
    app.onboarding_step = 0;
    let content = format!(
        "**First-launch onboarding started.**\n\n{}",
        format_onboarding_step(0)
    );
    if popup {
        app.open_info_popup_with_return("Onboarding", content, Some(AppMode::Normal));
    } else {
        app.push_message(ChatMessage::system(content));
    }
}
