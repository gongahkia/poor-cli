use super::*;

pub(crate) fn format_bootstrap_report(root: &Path) -> String {
    let project_kind = classify_project_kind(root);
    let commands = recommended_bootstrap_commands(root);
    let mut lines = vec![
        format!("**Solo Quickstart** (`{}`)", root.to_string_lossy()),
        format!("- Project type: `{project_kind}`"),
        String::new(),
        "**Recommended first commands**".to_string(),
    ];
    for command in commands {
        lines.push(format!("- `{command}`"));
    }
    lines.push(String::new());
    lines.push(
        "Suggested flow: `/doctor` -> `/focus start ...` -> `/workspace-map` -> `/resume`."
            .to_string(),
    );
    lines.push("Onboarding shortcut: `/onboarding 1`.".to_string());
    lines.join("\n")
}

fn estimate_token_cost(char_count: usize) -> usize {
    (char_count / 4).max(1)
}

fn is_binary_like_extension(ext: &str) -> bool {
    matches!(
        ext,
        "png"
            | "jpg"
            | "jpeg"
            | "gif"
            | "webp"
            | "bmp"
            | "ico"
            | "pdf"
            | "zip"
            | "gz"
            | "tar"
            | "jar"
            | "wasm"
            | "exe"
            | "dll"
            | "so"
            | "dylib"
            | "ttf"
            | "otf"
            | "woff"
            | "woff2"
            | "mp3"
            | "mp4"
            | "mov"
            | "avi"
    )
}

fn context_relevance_score(path: &Path) -> i32 {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();

    let mut score = match extension.as_str() {
        "rs" | "py" | "ts" | "tsx" | "js" | "jsx" | "go" | "java" | "kt" => 120,
        "toml" | "yaml" | "yml" | "json" => 80,
        "md" => 60,
        "sh" => 70,
        _ => 40,
    };

    if matches!(
        file_name.as_str(),
        "readme.md"
            | "cargo.toml"
            | "pyproject.toml"
            | "package.json"
            | "makefile"
            | "main.rs"
            | "main.py"
            | "app.py"
            | "index.ts"
            | "index.js"
    ) {
        score += 120;
    }
    if file_name.contains("test") {
        score += 40;
    }
    if file_name.contains("config") || file_name.ends_with(".env") {
        score += 30;
    }
    if file_name.contains(".lock") {
        score -= 40;
    }
    score
}

pub(crate) fn compute_context_budget_files(
    root: &Path,
    budget_tokens: usize,
    max_files: usize,
) -> (Vec<String>, usize) {
    let mut candidates = Vec::<(i32, String, usize)>::new();
    for path in collect_directory_files(root, 5000) {
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if is_binary_like_extension(&extension) {
            continue;
        }
        let byte_size = fs::metadata(&path)
            .ok()
            .map(|metadata| metadata.len() as usize)
            .unwrap_or(0);
        if byte_size == 0 {
            continue;
        }
        let relative = path
            .strip_prefix(root)
            .map(|rel| rel.to_string_lossy().to_string())
            .unwrap_or_else(|_| path.to_string_lossy().to_string());
        candidates.push((context_relevance_score(&path), relative, byte_size));
    }

    candidates.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.cmp(&b.1)));

    let mut selected = Vec::<String>::new();
    let mut used_tokens = 0usize;
    for (_, relative, byte_size) in candidates {
        if selected.len() >= max_files {
            break;
        }
        let estimated = estimate_token_cost(byte_size.min(12_000));
        if used_tokens + estimated > budget_tokens && !selected.is_empty() {
            break;
        }
        selected.push(relative);
        used_tokens += estimated;
    }

    (selected, used_tokens)
}

pub(crate) fn refresh_context_budget_state(app: &mut App) {
    let root = PathBuf::from(&app.cwd);
    if !root.is_dir() {
        app.context_budget_files.clear();
        app.context_budget_estimated_tokens = 0;
        return;
    }

    let (files, used_tokens) = compute_context_budget_files(&root, app.context_budget_tokens, 12);
    app.context_budget_files = files;
    app.context_budget_estimated_tokens = used_tokens;
}

pub(crate) fn refresh_workspace_status(app: &mut App) {
    if app.cwd.is_empty() {
        return;
    }

    let output = Command::new("git")
        .args(["-C", &app.cwd, "status", "-sb"])
        .output();
    let Ok(output) = output else {
        app.git_branch.clear();
        app.git_dirty = false;
        if app.resume_dashboard.git_summary.is_empty() {
            app.resume_dashboard.git_summary = "(git unavailable)".to_string();
        }
        return;
    };
    if !output.status.success() {
        app.git_branch.clear();
        app.git_dirty = false;
        app.resume_dashboard.git_summary = "(not a git repository)".to_string();
        return;
    }

    let status = String::from_utf8_lossy(&output.stdout).to_string();
    let mut lines = status.lines();
    let branch_line = lines
        .next()
        .unwrap_or("")
        .trim()
        .trim_start_matches("## ")
        .to_string();
    app.git_dirty = lines.next().is_some();
    app.git_branch = branch_line
        .split("...")
        .next()
        .unwrap_or(branch_line.as_str())
        .trim()
        .to_string();
    app.resume_dashboard.git_summary = if branch_line.is_empty() {
        "(git unavailable)".to_string()
    } else if app.git_dirty {
        format!("{branch_line} *dirty*")
    } else {
        branch_line
    };
}

pub(crate) fn refresh_resume_dashboard(app: &mut App, rpc_cmd_tx: &mpsc::Sender<RpcCommand>) {
    let mut dashboard = app.resume_dashboard.clone();
    dashboard.recent_edits = app.recent_edited_files.iter().take(5).cloned().collect();
    dashboard.git_summary = app.resume_dashboard.git_summary.clone();

    if let Ok(payload) = rpc_list_sessions_blocking(rpc_cmd_tx, 1) {
        let sessions = payload
            .get("sessions")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if let Some(first) = sessions.first() {
            let session_id = first
                .get("sessionId")
                .and_then(|value| value.as_str())
                .unwrap_or("(unknown)");
            let model = first
                .get("model")
                .and_then(|value| value.as_str())
                .unwrap_or("(unknown)");
            let message_count = first
                .get("messageCount")
                .and_then(|value| value.as_u64())
                .unwrap_or(0);
            dashboard.last_session_summary =
                format!("{session_id} on {model} ({message_count} messages)");
        }
    }

    if let Ok(payload) = rpc_list_checkpoints_blocking(rpc_cmd_tx, 5) {
        let checkpoints = payload
            .get("checkpoints")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        dashboard.recent_checkpoints = checkpoints
            .iter()
            .filter_map(|entry| entry.get("checkpointId").and_then(|value| value.as_str()))
            .take(5)
            .map(|value| value.to_string())
            .collect();
    }

    if let Ok(payload) = rpc_get_service_status_blocking(rpc_cmd_tx, None) {
        if let Some(services) = payload.get("services").and_then(|value| value.as_array()) {
            dashboard.active_services = services
                .iter()
                .filter(|entry| {
                    entry
                        .get("running")
                        .and_then(|value| value.as_bool())
                        .unwrap_or(false)
                })
                .filter_map(|entry| entry.get("name").and_then(|value| value.as_str()))
                .take(5)
                .map(|value| value.to_string())
                .collect();
        }
    }

    app.set_resume_dashboard(dashboard);
}

pub(crate) fn refresh_workspace_panels(_app: &mut App, _rpc_cmd_tx: &mpsc::Sender<RpcCommand>) {
    // workspace panels removed; nothing to refresh
}

pub(crate) fn resolve_explicit_context_map(
    app: &App,
    message: &str,
) -> Result<HashMap<String, String>, String> {
    let inline_specs = extract_at_references(message)?;
    let mut mapping = HashMap::new();
    for spec in inline_specs {
        let matches = resolve_context_spec(app, &spec);
        if matches.len() == 1 {
            mapping.insert(matches[0].to_string_lossy().to_string(), spec);
        }
    }
    Ok(mapping)
}

pub(crate) fn resolve_pinned_context_map(app: &App) -> HashMap<String, String> {
    let mut mapping = HashMap::new();
    for spec in &app.pinned_context_files {
        let matches = resolve_context_spec(app, spec);
        if matches.len() == 1 {
            mapping.insert(matches[0].to_string_lossy().to_string(), spec.clone());
        }
    }
    mapping
}

pub(crate) fn open_context_inspector_for_message(
    app: &mut App,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    message: String,
) -> Result<(), String> {
    let prepared = prepare_context_request(app, &message)?;
    let preview = rpc_get_context_explain_blocking(
        rpc_cmd_tx,
        &prepared.message,
        &prepared.explicit_files,
        &prepared.pinned_files,
        Some(app.context_budget_tokens),
    )?;

    let explicit_map = resolve_explicit_context_map(app, &message)?;
    let pinned_map = resolve_pinned_context_map(app);
    let files = preview
        .get("files")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|entry| {
            let path = entry
                .get("path")
                .and_then(|value| value.as_str())?
                .to_string();
            let source = entry
                .get("source")
                .and_then(|value| value.as_str())
                .unwrap_or("auto")
                .to_string();
            Some(ContextInspectorFile {
                explicit_spec: if source == "explicit" {
                    explicit_map.get(&path).cloned()
                } else if source == "pinned" {
                    pinned_map.get(&path).cloned()
                } else {
                    None
                },
                path: path.clone(),
                source,
                estimated_tokens: entry
                    .get("estimatedTokens")
                    .and_then(|value| value.as_u64())
                    .unwrap_or(0) as usize,
                reason: entry
                    .get("reason")
                    .and_then(|value| value.as_str())
                    .unwrap_or("")
                    .to_string(),
                include_full_content: entry
                    .get("includeFullContent")
                    .and_then(|value| value.as_bool())
                    .unwrap_or(false),
            })
        })
        .collect::<Vec<_>>();

    app.context_budget_files = files.iter().map(|file| file.path.clone()).collect();
    app.context_budget_estimated_tokens = preview
        .get("totalTokens")
        .and_then(|value| value.as_u64())
        .unwrap_or(0) as usize;
    app.open_context_inspector(ContextInspectorState {
        request_message: prepared.message,
        total_tokens: app.context_budget_estimated_tokens,
        budget_tokens: app.context_budget_tokens,
        truncated: preview
            .get("truncated")
            .and_then(|value| value.as_bool())
            .unwrap_or(false),
        message: preview
            .get("message")
            .and_then(|value| value.as_str())
            .unwrap_or("")
            .to_string(),
        keywords: preview
            .get("keywords")
            .and_then(|value| value.as_array())
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str().map(|value| value.to_string()))
                    .collect()
            })
            .unwrap_or_default(),
        files,
        selected_index: 0,
    });
    Ok(())
}

pub(crate) fn build_quick_open_items(app: &App, rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Vec<QuickOpenItem> {
    let mut items = Vec::new();

    for spec in input::SLASH_COMMANDS.iter() {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::Command,
            label: spec.command.to_string(),
            detail: spec.description.to_string(),
            value: spec.command.to_string(),
        });
    }

    for file in &app.pinned_context_files {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::File,
            label: file.clone(),
            detail: "pinned file".to_string(),
            value: file.clone(),
        });
    }

    for file in app.recent_edited_files.iter().take(10) {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::File,
            label: file.clone(),
            detail: "recent edit".to_string(),
            value: file.clone(),
        });
    }

    if let Ok(payload) = rpc_list_checkpoints_blocking(rpc_cmd_tx, 8) {
        if let Some(checkpoints) = payload
            .get("checkpoints")
            .and_then(|value| value.as_array())
        {
            for checkpoint in checkpoints.iter().take(8) {
                if let Some(checkpoint_id) = checkpoint
                    .get("checkpointId")
                    .and_then(|value| value.as_str())
                {
                    let description = checkpoint
                        .get("description")
                        .and_then(|value| value.as_str())
                        .unwrap_or("checkpoint");
                    items.push(QuickOpenItem {
                        kind: QuickOpenItemKind::Checkpoint,
                        label: checkpoint_id.to_string(),
                        detail: description.to_string(),
                        value: checkpoint_id.to_string(),
                    });
                }
            }
        }
    }

    for prompt in app.recent_prompts.iter().take(10) {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::Prompt,
            label: truncate_line(prompt, 42),
            detail: "recent prompt".to_string(),
            value: prompt.clone(),
        });
    }

    items
}

pub(crate) fn open_file_in_editor(path: &str) -> Result<(), String> {
    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".to_string());
    let mut parts = editor.split_whitespace();
    let Some(program) = parts.next() else {
        return Err("EDITOR is empty".to_string());
    };

    let mut command = Command::new(program);
    for arg in parts {
        command.arg(arg);
    }
    command.arg(path);

    command
        .spawn()
        .map_err(|error| format!("Failed to open `{path}` in {editor}: {error}"))?;
    Ok(())
}

pub(crate) fn command_data_dir(app: &App) -> PathBuf {
    Path::new(&app.cwd).join(".poor-cli")
}

pub(crate) fn focus_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("focus.json")
}

pub(crate) fn repo_memory_path(app: &App) -> PathBuf {
    command_data_dir(app).join("memory.md")
}

pub(crate) fn load_repo_memory(app: &App) -> Result<Option<String>, String> {
    let path = repo_memory_path(app);
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(&path)
        .map_err(|error| format!("Failed to read repo memory: {error}"))?;
    Ok(Some(content))
}

pub(crate) fn save_repo_memory(app: &App, content: &str) -> Result<PathBuf, String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root)
        .map_err(|error| format!("Failed to create data directory: {error}"))?;
    let path = repo_memory_path(app);
    fs::write(&path, content).map_err(|error| format!("Failed to write repo memory: {error}"))?;
    Ok(path)
}

pub(crate) fn load_focus_state(app: &App) -> Result<Option<FocusState>, String> {
    let path = focus_state_path(app);
    if !path.exists() {
        return Ok(None);
    }
    let content =
        fs::read_to_string(&path).map_err(|e| format!("Failed to read focus state: {e}"))?;
    let state: FocusState =
        serde_json::from_str(&content).map_err(|e| format!("Invalid focus state: {e}"))?;
    Ok(Some(state))
}

pub(crate) fn save_focus_state(app: &App, state: &FocusState) -> Result<(), String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root).map_err(|e| format!("Failed to create data directory: {e}"))?;
    let path = focus_state_path(app);
    let serialized = serde_json::to_string_pretty(state)
        .map_err(|e| format!("Failed to serialize focus state: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("Failed to persist focus state: {e}"))
}

pub(crate) fn profile_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("profile.json")
}

pub(crate) fn load_profile_state(app: &App) -> Result<Option<ProfileState>, String> {
    let path = profile_state_path(app);
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(path).map_err(|e| format!("Failed to read profile: {e}"))?;
    let profile: ProfileState =
        serde_json::from_str(&content).map_err(|e| format!("Invalid profile state: {e}"))?;
    Ok(Some(profile))
}

pub(crate) fn save_profile_state(app: &App, profile: &ProfileState) -> Result<(), String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root).map_err(|e| format!("Failed to create data directory: {e}"))?;
    let path = profile_state_path(app);
    let serialized = serde_json::to_string_pretty(profile)
        .map_err(|e| format!("Failed to serialize profile: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("Failed to write profile: {e}"))
}

pub(crate) fn apply_execution_profile(
    app: &mut App,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    profile_name: &str,
    persist: bool,
) -> Result<String, String> {
    let normalized = profile_name.trim().to_ascii_lowercase();
    let (response_mode, context_budget, permission_mode, iteration_cap, notes) =
        match normalized.as_str() {
            "speed" => (
                ResponseMode::Poor,
                3200usize,
                "auto-safe",
                30u32,
                "Optimized for fast iteration and lower token usage.",
            ),
            "safe" => (
                ResponseMode::Rich,
                6000usize,
                "prompt",
                40u32,
                "Balanced defaults with safer execution prompts.",
            ),
            "deep-review" | "deep" => (
                ResponseMode::Rich,
                9000usize,
                "prompt",
                60u32,
                "Expanded context and deeper analysis defaults.",
            ),
            _ => return Err("Unknown profile. Use one of: speed, safe, deep-review".to_string()),
        };

    app.execution_profile = if normalized == "deep" {
        "deep-review".to_string()
    } else {
        normalized
    };
    app.response_mode = response_mode;
    app.context_budget_tokens = context_budget;
    app.streaming.iteration_cap = iteration_cap;

    let _ = rpc_set_config_blocking(
        rpc_cmd_tx,
        "security.permission_mode",
        Value::String(permission_mode.to_string()),
    );
    let _ = rpc_set_config_blocking(
        rpc_cmd_tx,
        "ui.response_mode",
        Value::String(app.response_mode.as_str().to_string()),
    );
    let _ = rpc_set_config_blocking(
        rpc_cmd_tx,
        "agentic.max_iterations",
        Value::Number(serde_json::Number::from(iteration_cap)),
    );

    if persist {
        save_profile_state(
            app,
            &ProfileState {
                name: app.execution_profile.clone(),
            },
        )?;
    }

    Ok(format!(
        "Profile set to **{}**.\n- Response mode: `{}`\n- Permission mode: `{}`\n- Context budget: {} tokens\n- Iteration cap default: {}\n\n{}",
        app.execution_profile,
        app.response_mode.as_str(),
        permission_mode,
        app.context_budget_tokens,
        app.streaming.iteration_cap,
        notes
    ))
}

pub(crate) fn last_assistant_message(app: &App) -> Option<String> {
    app.messages
        .iter()
        .rev()
        .find(|m| matches!(m.role, MessageRole::Assistant))
        .map(|m| m.content.clone())
}

pub(crate) fn shell_escape_single_quotes(input: &str) -> String {
    format!("'{}'", input.replace('\'', "'\"'\"'"))
}

// ── Prompt library helpers ───────────────────────────────────────────

pub(crate) fn prompt_library_dir(app: &App) -> PathBuf {
    Path::new(&app.cwd).join(".poor-cli").join("prompts")
}

pub(crate) fn sanitize_prompt_name(name: &str) -> Result<String, String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("Prompt name cannot be empty".to_string());
    }

    if !trimmed
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return Err(
            "Prompt name must use only letters, numbers, '-' or '_' characters".to_string(),
        );
    }

    Ok(trimmed.to_string())
}

pub(crate) fn save_prompt(app: &App, name: &str, content: &str) -> Result<PathBuf, String> {
    let name = sanitize_prompt_name(name)?;
    let dir = prompt_library_dir(app);
    fs::create_dir_all(&dir).map_err(|e| format!("Failed to create prompts directory: {e}"))?;

    let path = dir.join(format!("{name}.txt"));
    fs::write(&path, content).map_err(|e| format!("Failed to save prompt: {e}"))?;
    Ok(path)
}

pub(crate) fn load_prompt(app: &App, name: &str) -> Result<String, String> {
    let name = sanitize_prompt_name(name)?;
    let path = prompt_library_dir(app).join(format!("{name}.txt"));
    fs::read_to_string(&path).map_err(|_| format!("Prompt not found: {name}"))
}

pub(crate) fn list_prompts(app: &App) -> Result<Vec<(String, String)>, String> {
    let dir = prompt_library_dir(app);
    if !dir.exists() {
        return Ok(vec![]);
    }

    let mut entries = vec![];
    for entry in fs::read_dir(&dir).map_err(|e| format!("Failed to read prompts directory: {e}"))? {
        let entry = entry.map_err(|e| format!("Failed to inspect prompt entry: {e}"))?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("txt") {
            continue;
        }

        let name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();
        let preview = fs::read_to_string(&path)
            .unwrap_or_else(|_| "(unable to read)".to_string())
            .replace('\n', " ");
        entries.push((name, truncate_line(preview.trim(), 60)));
    }

    entries.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(entries)
}
