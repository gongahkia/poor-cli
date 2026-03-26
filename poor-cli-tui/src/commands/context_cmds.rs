use super::super::*;
use super::core::show_command_info_popup;

pub(super) fn handle_context_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    _tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    _launch: &BackendLaunchContext,
    _cancel_token: &Arc<AtomicBool>,
    _watch_state: &mut WatchState,
    _qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered.starts_with("/add ") {
        let spec = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if spec.is_empty() {
            show_command_info_popup(app, raw, "Usage: /add <path>".to_string());
            return Some(false);
        }

        let resolved = resolve_context_spec(app, spec);
        if resolved.is_empty() {
            app.push_message(ChatMessage::error(format!("No files matched: {spec}")));
            return Some(false);
        }

        let mut added = 0usize;
        for path in resolved {
            let display = display_project_path(app, &path);
            if !app.pinned_context_files.contains(&display) {
                app.pinned_context_files.push(display);
                added += 1;
            }
        }
        app.pinned_context_files.sort();
        app.pinned_context_files.dedup();

        if added == 0 {
            show_command_info_popup(
                app,
                raw,
                "All matched files were already pinned.".to_string(),
            );
        } else {
            app.set_status(format!(
                "Pinned {added} context file(s); total: {}",
                app.pinned_context_files.len()
            ));
        }
        return Some(false);
    }

    if lowered == "/drop" {
        if app.pinned_context_files.is_empty() {
            let msg = "No pinned context files to drop.";
            show_command_info_popup(app, raw, if app.mascot_enabled { poor_cli_tui::onboarding::owl_message(1, msg) } else { msg.to_string() });
        } else {
            let items: Vec<ListSelectorItem> = app.pinned_context_files.iter().map(|p| {
                ListSelectorItem { label: p.clone(), value: p.clone() }
            }).collect();
            app.open_list_selector(ListSelectorState {
                title: format!("Drop File ({})", items.len()), items, selected_idx: 0,
                command_template: "/drop {}".to_string(),
                action_hint_override: None,
            });
        }
        return Some(false);
    }

    if lowered.starts_with("/drop ") {
        let spec = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if spec.is_empty() {
            show_command_info_popup(app, raw, "Usage: /drop <path>".to_string());
            return Some(false);
        }

        let before = app.pinned_context_files.len();
        app.pinned_context_files
            .retain(|p| p != spec && !p.ends_with(&format!("/{spec}")));
        let removed = before.saturating_sub(app.pinned_context_files.len());

        if removed == 0 {
            show_command_info_popup(app, raw, format!("No pinned file matched: {spec}"));
        } else {
            app.set_status(format!(
                "Removed {removed} pinned file(s); total: {}",
                app.pinned_context_files.len()
            ));
        }
        return Some(false);
    }

    if lowered == "/files" {
        if app.pinned_context_files.is_empty() {
            show_command_info_popup(
                app,
                raw,
                if app.mascot_enabled { poor_cli_tui::onboarding::owl_message(0, "No pinned context files.\nUse /add <path> or @path in a prompt.") } else { "No pinned context files.\nUse /add <path> or @path in a prompt.".to_string() },
            );
        } else {
            let mut lines = vec![
                format!(
                    "**Pinned Context Files ({}):**",
                    app.pinned_context_files.len()
                ),
                String::new(),
            ];
            for file in &app.pinned_context_files {
                lines.push(format!("- {file}"));
            }
            show_command_info_popup(app, raw, lines.join("\n"));
        }
        return Some(false);
    }

    if lowered == "/clear-files" {
        let removed = app.pinned_context_files.len();
        app.pinned_context_files.clear();
        app.set_status(format!("Cleared {removed} pinned context file(s)"));
        return Some(false);
    }

    if lowered == "/focus" || lowered.starts_with("/focus ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();

        if subcommand.is_empty() {
            let items = vec![
                ListSelectorItem { label: "status: Show focus state".into(), value: "status".into() },
                ListSelectorItem { label: "start: Start a focus session".into(), value: "start".into() },
                ListSelectorItem { label: "done: End focus session".into(), value: "done".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "Focus".into(), items, selected_idx: 0,
                command_template: "/focus {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }

        if subcommand == "status" {
            match load_focus_state(app) {
                Ok(Some(state)) => {
                    show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Focus Status**\n- Goal: {}\n- Constraints: {}\n- Definition of done: {}\n- Started: {}\n- Completed: {}",
                            if state.goal.is_empty() { "(none)" } else { &state.goal },
                            if state.constraints.is_empty() {
                                "(none)"
                            } else {
                                &state.constraints
                            },
                            if state.definition_of_done.is_empty() {
                                "(none)"
                            } else {
                                &state.definition_of_done
                            },
                            if state.started_at.is_empty() {
                                "(unknown)"
                            } else {
                                &state.started_at
                            },
                            if state.completed { "yes" } else { "no" }
                        ),
                    );
                }
                Ok(None) => show_command_info_popup(
                    app,
                    raw,
                    "No active focus.\nUse `/focus start <goal> [|| constraints || definition-of-done]`."
                        .to_string(),
                ),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return Some(false);
        }

        if subcommand == "start" {
            let payload = raw.splitn(3, ' ').nth(2).map(str::trim).unwrap_or("");
            if payload.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /focus start <goal> [|| constraints || definition-of-done]".to_string(),
                );
                return Some(false);
            }
            let parts = payload.split("||").map(str::trim).collect::<Vec<_>>();
            let state = FocusState {
                goal: parts.first().copied().unwrap_or("").to_string(),
                constraints: parts.get(1).copied().unwrap_or("").to_string(),
                definition_of_done: parts.get(2).copied().unwrap_or("").to_string(),
                started_at: format!("{}", unix_ts_millis()),
                completed: false,
            };
            match save_focus_state(app, &state) {
                Ok(()) => show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Focus started.\n- Goal: {}\n- Constraints: {}\n- Definition of done: {}",
                        if state.goal.is_empty() {
                            "(none)"
                        } else {
                            &state.goal
                        },
                        if state.constraints.is_empty() {
                            "(none)"
                        } else {
                            &state.constraints
                        },
                        if state.definition_of_done.is_empty() {
                            "(none)"
                        } else {
                            &state.definition_of_done
                        }
                    ),
                ),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return Some(false);
        }

        if subcommand == "done" {
            match load_focus_state(app) {
                Ok(Some(mut state)) => {
                    state.completed = true;
                    match save_focus_state(app, &state) {
                        Ok(()) => {
                            show_command_info_popup(app, raw, "Focus marked complete.".to_string())
                        }
                        Err(e) => app.push_message(ChatMessage::error(e)),
                    }
                }
                Ok(None) => {
                    show_command_info_popup(app, raw, "No active focus to complete.".to_string())
                }
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return Some(false);
        }

        show_command_info_popup(app, raw, "Usage: /focus start|status|done".to_string());
        return Some(false);
    }

    if lowered == "/resume" {
        let mut lines = vec!["**Resume Snapshot**".to_string(), String::new()];
        if let Ok(Some(state)) = load_focus_state(app) {
            if !state.goal.is_empty() {
                lines.push(format!("- Focus goal: {}", state.goal));
            }
            if !state.completed {
                lines.push("- Focus status: active".to_string());
            }
        }

        match rpc_list_sessions_blocking(rpc_cmd_tx, 1) {
            Ok(payload) => {
                let sessions = payload
                    .get("sessions")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if let Some(first) = sessions.first() {
                    let session_id = first
                        .get("sessionId")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)");
                    let model = first
                        .get("model")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)");
                    let message_count = first
                        .get("messageCount")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    lines.push(format!(
                        "- Last session: `{session_id}` on `{model}` ({message_count} messages)"
                    ));
                }
            }
            Err(e) => lines.push(format!("- Session lookup failed: {e}")),
        }

        match rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, "git status -sb", Some(20), 25)
        {
            Ok(status) => lines.push(format!("- Git status: `{}`", first_line(&status))),
            Err(e) => lines.push(format!("- Git status unavailable: {e}")),
        }

        match rpc_list_checkpoints_blocking(rpc_cmd_tx, 5) {
            Ok(payload) => {
                let checkpoints = payload
                    .get("checkpoints")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                lines.push(format!("- Recent checkpoints: {}", checkpoints.len()));
            }
            Err(e) => lines.push(format!("- Checkpoint lookup failed: {e}")),
        }

        lines.push(String::new());
        lines.push(
            "Suggested next steps: `/status`, `/history 10`, `/checkpoints`, `/review`."
                .to_string(),
        );
        show_command_info_popup(app, raw, lines.join("\n"));
        return Some(false);
    }

    if lowered == "/context-budget" || lowered.starts_with("/context-budget ") {
        if let Some(raw_budget) = raw.split_whitespace().nth(1) {
            match raw_budget.parse::<usize>() {
                Ok(value) => {
                    app.context_budget_tokens = value.clamp(1000, 20000);
                }
                Err(_) => {
                    show_command_info_popup(
                        app,
                        raw,
                        "Usage: /context-budget [token-budget]".to_string(),
                    );
                    return Some(false);
                }
            }
        }

        let preview_message = app.last_user_message.clone().unwrap_or_default();
        match open_context_inspector_for_message(app, rpc_cmd_tx, preview_message) {
            Ok(()) => {}
            Err(error) => app.push_message(ChatMessage::error(format!(
                "Failed to preview context budget: {error}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/context" || lowered == "/context explain" {
        let preview_message = app.last_user_message.clone().unwrap_or_default();
        match open_context_inspector_for_message(app, rpc_cmd_tx, preview_message) {
            Ok(()) => {}
            Err(error) => app.push_message(ChatMessage::error(format!(
                "Failed to open context inspector: {error}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/workspace-map" || lowered.starts_with("/workspace-map ") {
        let root_raw = raw.split_once(' ').map(|x| x.1)
            .map(str::trim)
            .filter(|value| !value.is_empty());
        let root = root_raw
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(&app.cwd));
        let files = collect_directory_files(&root, 4000);
        if files.is_empty() {
            show_command_info_popup(app, raw, "No files found for workspace map.".to_string());
            return Some(false);
        }

        let mut ext_counts = HashMap::<String, usize>::new();
        let mut entrypoints = Vec::<String>::new();
        for file in &files {
            if let Some(ext) = file.extension().and_then(|v| v.to_str()) {
                *ext_counts.entry(ext.to_string()).or_insert(0) += 1;
            }
            if let Some(name) = file.file_name().and_then(|v| v.to_str()) {
                if matches!(
                    name,
                    "Cargo.toml"
                        | "pyproject.toml"
                        | "package.json"
                        | "Makefile"
                        | "main.rs"
                        | "main.py"
                ) {
                    entrypoints.push(file.to_string_lossy().to_string());
                }
            }
        }
        let mut ext_pairs = ext_counts.into_iter().collect::<Vec<_>>();
        ext_pairs.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
        let ext_summary = ext_pairs
            .into_iter()
            .take(8)
            .map(|(ext, count)| format!("{ext}:{count}"))
            .collect::<Vec<_>>()
            .join(", ");
        let mut lines = vec![
            format!("**Workspace Map:** `{}`", root.to_string_lossy()),
            format!("- Total files indexed: {}", files.len()),
            format!("- Top extensions: {ext_summary}"),
        ];
        if !entrypoints.is_empty() {
            lines.push("- Entrypoints:".to_string());
            for entry in entrypoints.into_iter().take(10) {
                lines.push(format!("  - `{entry}`"));
            }
        }
        show_command_info_popup(app, raw, lines.join("\n"));
        return Some(false);
    }

    if lowered == "/bootstrap" || lowered.starts_with("/bootstrap ") {
        let root_raw = raw.split_once(' ').map(|x| x.1)
            .map(str::trim)
            .filter(|value| !value.is_empty());
        let root = root_raw
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(&app.cwd));
        show_command_info_popup(app, raw, format_bootstrap_report(&root));
        return Some(false);
    }

    if lowered == "/profile" || lowered.starts_with("/profile ") {
        let selected = raw
            .split_whitespace()
            .nth(1)
            .map(|value| value.trim().to_ascii_lowercase())
            .unwrap_or_else(|| "status".to_string());
        if selected == "status" {
            let profiles = [("speed", "smaller context, terse output, faster loop"),
                ("safe", "balanced defaults, review-oriented safety"),
                ("deep-review", "larger context, richer analysis depth")];
            let items: Vec<ListSelectorItem> = profiles.iter().map(|(name, desc)| {
                let active = if *name == app.execution_profile.as_str() { " (active)" } else { "" };
                ListSelectorItem {
                    label: format!("{name}{active}: {desc}"),
                    value: name.to_string(),
                }
            }).collect();
            app.open_list_selector(ListSelectorState {
                title: "Execution Profile".to_string(),
                items,
                selected_idx: 0,
                command_template: "/profile {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }

        match apply_execution_profile(app, rpc_cmd_tx, &selected, true) {
            Ok(summary) => {
                refresh_context_budget_state(app);
                show_command_info_popup(app, raw, summary);
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return Some(false);
    }

    None
}
