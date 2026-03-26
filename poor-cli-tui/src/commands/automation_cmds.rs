use super::super::*;
use super::core::show_command_info_popup;
use super::tasks::{format_runs_payload, format_task_detail};

pub(super) fn handle_automation_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    _launch: &BackendLaunchContext,
    _cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered == "/autopilot" || lowered.starts_with("/autopilot ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();
        if subcommand.is_empty() {
            let items = vec![
                ListSelectorItem { label: "status: Show autopilot status".into(), value: "status".into() },
                ListSelectorItem { label: "start: Enable autopilot".into(), value: "start".into() },
                ListSelectorItem { label: "stop: Disable autopilot".into(), value: "stop".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "Autopilot".into(), items, selected_idx: 0,
                command_template: "/autopilot {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }
        if subcommand == "status" {
            show_command_info_popup(
                app,
                raw,
                format!(
                    "Autopilot: {}\nIteration cap: {}",
                    if app.autopilot_enabled {
                        "enabled"
                    } else {
                        "disabled"
                    },
                    app.streaming.iteration_cap
                ),
            );
            return Some(false);
        }
        if subcommand == "start" {
            let allow_risky = args
                .iter()
                .any(|value| value.trim().eq_ignore_ascii_case("--allow-risky"));
            if !allow_risky {
                if let Ok(cfg) = rpc_get_config_blocking(rpc_cmd_tx) {
                    let mode = cfg
                        .get("permissionMode")
                        .and_then(|value| value.as_str())
                        .unwrap_or("prompt");
                    if mode == "danger-full-access" {
                        show_command_info_popup(
                            app,
                            raw,
                            "Autopilot guardrail blocked start because permission mode is `danger-full-access`.\nUse `/permission-mode prompt` or rerun with `/autopilot start <cap> --allow-risky`."
                                .to_string(),
                        );
                        return Some(false);
                    }
                }
            }
            let cap = args
                .get(2)
                .and_then(|raw| raw.parse::<u32>().ok())
                .unwrap_or_else(|| {
                    if app.execution_profile == "speed" {
                        30
                    } else if app.execution_profile == "deep-review" {
                        60
                    } else {
                        40
                    }
                })
                .clamp(5, 120);
            if let Err(error) = rpc_set_config_blocking(
                rpc_cmd_tx,
                "agentic.max_iterations",
                Value::Number(serde_json::Number::from(cap)),
            ) {
                show_command_info_popup(app, raw, format!("Failed to enable autopilot: {error}"));
                return Some(false);
            }
            app.autopilot_enabled = true;
            app.streaming.iteration_cap = cap;
            show_command_info_popup(
                app,
                raw,
                format!("Autopilot enabled with iteration cap {cap}."),
            );
            return Some(false);
        }
        if subcommand == "stop" {
            if let Err(error) = rpc_set_config_blocking(
                rpc_cmd_tx,
                "agentic.max_iterations",
                Value::Number(serde_json::Number::from(25u32)),
            ) {
                show_command_info_popup(app, raw, format!("Failed to disable autopilot: {error}"));
                return Some(false);
            }
            app.autopilot_enabled = false;
            app.streaming.iteration_cap = 25;
            show_command_info_popup(
                app,
                raw,
                "Autopilot disabled. Iteration cap reset to 25.".to_string(),
            );
            return Some(false);
        }
        show_command_info_popup(
            app,
            raw,
            "Usage: /autopilot start [cap] [--allow-risky]\n       /autopilot stop\n       /autopilot status".to_string(),
        );
        return Some(false);
    }

    if lowered == "/sandbox" || lowered.starts_with("/sandbox ") {
        let selected = raw.split_whitespace().nth(1).unwrap_or("").trim();
        if selected.is_empty() {
            let current = rpc_get_sandbox_status_blocking(rpc_cmd_tx)
                .ok()
                .and_then(|p| p.get("sandboxPreset").and_then(|v| v.as_str()).map(String::from))
                .unwrap_or_default();
            let presets = [
                ("read-only", "Restrict all file writes"),
                ("review-only", "Read + review access only"),
                ("workspace-write", "Write within workspace"),
                ("full-access", "Unrestricted file access"),
            ];
            let items: Vec<ListSelectorItem> = presets.iter().map(|(name, desc)| {
                let active = if *name == current { " (active)" } else { "" };
                ListSelectorItem { label: format!("{name}{active}: {desc}"), value: name.to_string() }
            }).collect();
            app.open_list_selector(ListSelectorState {
                title: "Sandbox Preset".into(), items, selected_idx: 0,
                command_template: "/sandbox {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }
        match rpc_set_config_blocking(
            rpc_cmd_tx,
            "sandbox.default_preset",
            Value::String(selected.to_string()),
        ) {
            Ok(_) => {
                app.permission_mode_label = selected.to_string();
                app.set_status(format!("Sandbox preset set to `{selected}`"));
            }
            Err(error) => {
                show_command_info_popup(app, raw, format!("Failed to set sandbox preset: {error}"))
            }
        }
        return Some(false);
    }

    if lowered == "/skills" || lowered.starts_with("/skills ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("list")
            .trim()
            .to_ascii_lowercase();
        if subcommand == "list" {
            match rpc_list_skills_blocking(rpc_cmd_tx) {
                Ok(payload) => {
                    let skills = payload
                        .get("skills")
                        .and_then(|value| value.as_array())
                        .cloned()
                        .unwrap_or_default();
                    if skills.is_empty() {
                        show_command_info_popup(app, raw, "No skills found.".to_string());
                        return Some(false);
                    }
                    let items: Vec<ListSelectorItem> = skills.iter().map(|skill| {
                        let name = skill.get("name").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                        let description = skill.get("description").and_then(|v| v.as_str()).unwrap_or("");
                        let scope = skill.get("scope").and_then(|v| v.as_str()).unwrap_or("user");
                        ListSelectorItem {
                            label: format!("{name} ({scope}) {description}"),
                            value: name.to_string(),
                        }
                    }).collect();
                    app.open_list_selector(ListSelectorState {
                        title: "Skills".to_string(),
                        items,
                        selected_idx: 0,
                        command_template: "/skills show {}".to_string(),
                        action_hint_override: None,
                    });
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to list skills: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "show" {
            let name = args.get(2).copied().unwrap_or("").trim();
            if name.is_empty() {
                show_command_info_popup(app, raw, "Usage: /skills show <name>".to_string());
                return Some(false);
            }
            match rpc_get_skill_blocking(rpc_cmd_tx, name) {
                Ok(payload) => {
                    let content = payload
                        .get("content")
                        .and_then(|value| value.as_str())
                        .unwrap_or("");
                    show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Skill** `{name}`\n\n```markdown\n{}\n```",
                            truncate_block(content, 6000)
                        ),
                    );
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to load skill: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "run" {
            let tail = args.get(2).copied().unwrap_or("").trim();
            let mut parts = tail.splitn(2, ' ');
            let name = parts.next().unwrap_or("").trim();
            let request = parts.next().unwrap_or("").trim();
            if name.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /skills run <name> [request]".to_string(),
                );
                return Some(false);
            }
            match rpc_get_skill_blocking(rpc_cmd_tx, name) {
                Ok(payload) => {
                    let content = payload
                        .get("content")
                        .and_then(|value| value.as_str())
                        .unwrap_or("");
                    let prompt = if request.is_empty() {
                        format!("[Skill: {name}]\n\n{content}")
                    } else {
                        format!("[Skill: {name}]\n\n{content}\n\n[User request]\n{request}")
                    };
                    app.prompt_queue
                        .push_back(poor_cli_tui::app::QueuedPrompt::automation(
                            format!("[skill] {name}"),
                            prompt,
                        ));
                    app.set_status(format!("Queued skill `{name}`"));
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to run skill: {error}"))
                }
            }
            return Some(false);
        }
        show_command_info_popup(
            app,
            raw,
            "Usage: /skills list\n       /skills show <name>\n       /skills run <name> [request]"
                .to_string(),
        );
        return Some(false);
    }

    if lowered == "/commands" || lowered.starts_with("/commands ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("list")
            .trim()
            .to_ascii_lowercase();
        if subcommand == "list" {
            match rpc_list_custom_commands_blocking(rpc_cmd_tx) {
                Ok(payload) => {
                    let commands = payload
                        .get("commands")
                        .and_then(|value| value.as_array())
                        .cloned()
                        .unwrap_or_default();
                    if commands.is_empty() {
                        show_command_info_popup(app, raw, "No custom commands found.".to_string());
                        return Some(false);
                    }
                    let items: Vec<ListSelectorItem> = commands.iter().map(|command| {
                        let name = command.get("name").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                        let description = command.get("description").and_then(|v| v.as_str()).unwrap_or("");
                        let scope = command.get("scope").and_then(|v| v.as_str()).unwrap_or("user");
                        ListSelectorItem {
                            label: format!("{name} ({scope}) {description}"),
                            value: name.to_string(),
                        }
                    }).collect();
                    app.open_list_selector(ListSelectorState {
                        title: "Custom Commands".to_string(),
                        items,
                        selected_idx: 0,
                        command_template: "/commands show {}".to_string(),
                        action_hint_override: None,
                    });
                }
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to list custom commands: {error}"),
                ),
            }
            return Some(false);
        }
        if subcommand == "show" {
            let name = args.get(2).copied().unwrap_or("").trim();
            if name.is_empty() {
                show_command_info_popup(app, raw, "Usage: /commands show <name>".to_string());
                return Some(false);
            }
            match rpc_get_custom_command_blocking(rpc_cmd_tx, name) {
                Ok(payload) => {
                    let template = payload
                        .get("template")
                        .and_then(|value| value.as_str())
                        .unwrap_or("");
                    show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Command** `{name}`\n\n```markdown\n{}\n```",
                            truncate_block(template, 6000)
                        ),
                    );
                }
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to load custom command: {error}"),
                ),
            }
            return Some(false);
        }
        if subcommand == "run" {
            let tail = args.get(2).copied().unwrap_or("").trim();
            let mut parts = tail.splitn(2, ' ');
            let name = parts.next().unwrap_or("").trim();
            let args_text = parts.next().unwrap_or("").trim();
            if name.is_empty() {
                show_command_info_popup(app, raw, "Usage: /commands run <name> [args]".to_string());
                return Some(false);
            }
            match rpc_run_custom_command_blocking(rpc_cmd_tx, name, args_text) {
                Ok(payload) => {
                    let content = payload
                        .get("content")
                        .and_then(|value| value.as_str())
                        .unwrap_or("");
                    app.push_message(ChatMessage::assistant(content.to_string()));
                }
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to run custom command: {error}"),
                ),
            }
            return Some(false);
        }
        show_command_info_popup(
            app,
            raw,
            "Usage: /commands list\n       /commands show <name>\n       /commands run <name> [args]".to_string(),
        );
        return Some(false);
    }

    if lowered == "/inbox" {
        match rpc_list_tasks_blocking(rpc_cmd_tx, true) {
            Ok(payload) => {
                let tasks = payload.get("tasks").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                if tasks.is_empty() {
                    show_command_info_popup(app, raw, "Inbox is empty.".to_string());
                } else {
                    let items: Vec<ListSelectorItem> = tasks.iter().map(|task| {
                        let task_id = task.get("taskId").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                        let status = task.get("status").and_then(|v| v.as_str()).unwrap_or("unknown");
                        let title = task.get("title").and_then(|v| v.as_str()).unwrap_or("(untitled)");
                        ListSelectorItem {
                            label: format!("{task_id} [{status}] {title}"),
                            value: task_id.to_string(),
                        }
                    }).collect();
                    app.open_list_selector(ListSelectorState {
                        title: "Inbox".to_string(),
                        items,
                        selected_idx: 0,
                        command_template: "/task open {}".to_string(),
                        action_hint_override: None,
                    });
                }
            }
            Err(error) => show_command_info_popup(app, raw, format!("Failed to load inbox: {error}")),
        }
        return Some(false);
    }

    if lowered == "/task"
        || lowered.starts_with("/task ")
        || lowered == "/tasks"
        || lowered.starts_with("/tasks ")
    {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("list")
            .trim()
            .to_ascii_lowercase();
        if subcommand == "list" {
            match rpc_list_tasks_blocking(rpc_cmd_tx, false) {
                Ok(payload) => {
                    let tasks = payload.get("tasks").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                    if tasks.is_empty() {
                        show_command_info_popup(app, raw, "No tasks found.".to_string());
                    } else {
                        let items: Vec<ListSelectorItem> = tasks.iter().map(|task| {
                            let task_id = task.get("taskId").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                            let status = task.get("status").and_then(|v| v.as_str()).unwrap_or("unknown");
                            let title = task.get("title").and_then(|v| v.as_str()).unwrap_or("(untitled)");
                            ListSelectorItem {
                                label: format!("{task_id} [{status}] {title}"),
                                value: task_id.to_string(),
                            }
                        }).collect();
                        app.open_list_selector(ListSelectorState {
                            title: "Tasks".to_string(),
                            items,
                            selected_idx: 0,
                            command_template: "/task open {}".to_string(),
                            action_hint_override: None,
                        });
                    }
                }
                Err(error) => show_command_info_popup(app, raw, format!("Failed to load tasks: {error}")),
            }
            return Some(false);
        }
        if subcommand == "open" || subcommand == "show" {
            let task_id = args.get(2).copied().unwrap_or("").trim();
            if task_id.is_empty() {
                show_command_info_popup(app, raw, "Usage: /task open <task-id>".to_string());
                return Some(false);
            }
            match rpc_get_task_blocking(rpc_cmd_tx, task_id) {
                Ok(payload) => show_command_info_popup(app, raw, format_task_detail(&payload)),
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to load task: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "create" || subcommand == "add" {
            let prompt = args.get(2).copied().unwrap_or("").trim();
            if prompt.is_empty() {
                show_command_info_popup(app, raw, "Usage: /task create <prompt>".to_string());
                return Some(false);
            }
            let sandbox_preset = rpc_get_sandbox_status_blocking(rpc_cmd_tx)
                .ok()
                .and_then(|payload| {
                    payload
                        .get("sandboxPreset")
                        .and_then(|value| value.as_str())
                        .map(|value| value.to_string())
                })
                .unwrap_or_else(|| "workspace-write".to_string());
            let requires_approval =
                matches!(sandbox_preset.as_str(), "workspace-write" | "full-access");
            let auto_start = !requires_approval;
            match rpc_create_task_blocking(
                rpc_cmd_tx,
                &truncate_line(prompt, 80),
                prompt,
                &sandbox_preset,
                "manual",
                auto_start,
                requires_approval,
            ) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_task_detail(&payload))
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to create task: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "approve" || subcommand == "done" {
            let task_id = args.get(2).copied().unwrap_or("").trim();
            if task_id.is_empty() {
                show_command_info_popup(app, raw, "Usage: /task approve <task-id>".to_string());
                return Some(false);
            }
            match rpc_approve_task_blocking(rpc_cmd_tx, task_id) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_task_detail(&payload))
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to approve task: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "cancel" || subcommand == "drop" {
            let task_id = args.get(2).copied().unwrap_or("").trim();
            if task_id.is_empty() {
                show_command_info_popup(app, raw, "Usage: /task cancel <task-id>".to_string());
                return Some(false);
            }
            match rpc_cancel_task_blocking(rpc_cmd_tx, task_id) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_task_detail(&payload))
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to cancel task: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "retry" {
            let task_id = args.get(2).copied().unwrap_or("").trim();
            if task_id.is_empty() {
                show_command_info_popup(app, raw, "Usage: /task retry <task-id>".to_string());
                return Some(false);
            }
            match rpc_retry_task_blocking(rpc_cmd_tx, task_id) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_task_detail(&payload))
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to retry task: {error}"))
                }
            }
            return Some(false);
        }
        if subcommand == "replay" {
            let task_id = args.get(2).copied().unwrap_or("").trim();
            if task_id.is_empty() {
                show_command_info_popup(app, raw, "Usage: /task replay <task-id>".to_string());
                return Some(false);
            }
            match rpc_replay_task_blocking(rpc_cmd_tx, task_id) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_task_detail(&payload))
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to replay task: {error}"))
                }
            }
            return Some(false);
        }
        show_command_info_popup(
            app,
            raw,
            "Usage: /task list\n       /task create <prompt>\n       /task open <task-id>\n       /task approve <task-id>\n       /task cancel <task-id>\n       /task retry <task-id>\n       /task replay <task-id>".to_string(),
        );
        return Some(false);
    }

    if lowered == "/automation" || lowered.starts_with("/automation ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();
        if subcommand.is_empty() || subcommand == "help" {
            let items = vec![
                ListSelectorItem { label: "history: View automation run history".into(), value: "history".into() },
                ListSelectorItem { label: "replay: Replay an automation run".into(), value: "replay".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "Automation".into(), items, selected_idx: 0,
                command_template: "/automation {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }
        if subcommand == "history" {
            let automation_id = args.get(2).copied().unwrap_or("").trim();
            if automation_id.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /automation history <automation-id> [limit]".to_string(),
                );
                return Some(false);
            }
            let limit = args
                .get(3)
                .and_then(|value| value.parse::<u64>().ok())
                .unwrap_or(20);
            match rpc_get_automation_history_blocking(rpc_cmd_tx, automation_id, limit) {
                Ok(payload) => show_command_info_popup(
                    app,
                    raw,
                    format_runs_payload(&payload, "**Automation History**"),
                ),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to load automation history: {error}"),
                ),
            }
            return Some(false);
        }
        if subcommand == "replay" {
            let automation_id = args.get(2).copied().unwrap_or("").trim();
            if automation_id.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /automation replay <automation-id>".to_string(),
                );
                return Some(false);
            }
            match rpc_replay_automation_blocking(rpc_cmd_tx, automation_id) {
                Ok(payload) => show_command_info_popup(app, raw, format_task_detail(&payload)),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to replay automation: {error}"),
                ),
            }
            return Some(false);
        }
        show_command_info_popup(
            app,
            raw,
            "Usage: /automation history <automation-id> [limit]\n       /automation replay <automation-id>"
                .to_string(),
        );
        return Some(false);
    }

    if lowered == "/qa" || lowered.starts_with("/qa ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();

        if subcommand.is_empty() {
            let items = vec![
                ListSelectorItem { label: "status: Show QA watch status".into(), value: "status".into() },
                ListSelectorItem { label: "start: Start QA watch".into(), value: "start".into() },
                ListSelectorItem { label: "stop: Stop QA watch".into(), value: "stop".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "QA Watch".into(), items, selected_idx: 0,
                command_template: "/qa {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }

        if subcommand == "status" {
            let status = if qa_watch_state.is_running() {
                "running"
            } else {
                "stopped"
            };
            show_command_info_popup(
                app,
                raw,
                format!(
                    "**QA Watch**\n- Status: {status}\n- Directory: {}\n- Command: {}",
                    qa_watch_state
                        .directory
                        .as_deref()
                        .unwrap_or(app.cwd.as_str()),
                    qa_watch_state.command.as_deref().unwrap_or("(not set)")
                ),
            );
            return Some(false);
        }

        if subcommand == "stop" {
            if qa_watch_state.is_running() {
                qa_watch_state.stop();
                app.qa_mode_enabled = false;
                app.qa_command.clear();
                app.set_status("QA watch stopped");
            } else {
                show_command_info_popup(app, raw, "QA watch is not running.".to_string());
            }
            return Some(false);
        }

        if subcommand == "start" {
            if qa_watch_state.is_running() {
                show_command_info_popup(
                    app,
                    raw,
                    "QA watch is already running. Use `/qa stop` first.".to_string(),
                );
                return Some(false);
            }

            let tail = raw
                .split_once(' ')
                .map(|(_, rest)| rest.trim())
                .and_then(|rest| rest.split_once(' ').map(|(_, after)| after.trim()))
                .unwrap_or("");
            let mut directory = app.cwd.clone();
            let mut command = watcher::default_qa_command_for_workspace(Path::new(&app.cwd));

            if !tail.is_empty() {
                let mut parts = tail.split_whitespace();
                if let Some(first) = parts.next() {
                    if Path::new(first).is_dir() {
                        directory = first.to_string();
                        let rest = parts.collect::<Vec<_>>().join(" ");
                        if !rest.trim().is_empty() {
                            command = rest.trim().to_string();
                        }
                    } else {
                        command = tail.to_string();
                    }
                }
            }

            if !Path::new(&directory).is_dir() {
                app.push_message(ChatMessage::error(format!(
                    "Directory not found: {directory}"
                )));
                return Some(false);
            }

            let stop = Arc::new(AtomicBool::new(false));
            let watch_tx = watch_msg_sender(tx);
            let handle = watcher::spawn_qa_watch_worker(
                directory.clone(),
                command.clone(),
                watch_tx,
                stop.clone(),
            );
            qa_watch_state.stop_flag = Some(stop);
            qa_watch_state.handle = Some(handle);
            qa_watch_state.directory = Some(directory.clone());
            qa_watch_state.command = Some(command.clone());
            app.qa_mode_enabled = true;
            app.qa_command = command.clone();
            app.set_status(format!("QA watch started: `{command}` on `{directory}`"));
            return Some(false);
        }

        show_command_info_popup(
            app,
            raw,
            "Usage: /qa start [dir] [command...]\n       /qa stop\n       /qa status".to_string(),
        );
        return Some(false);
    }

    if lowered.starts_with("/watch ") {
        let directory = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if directory.is_empty() {
            show_command_info_popup(app, raw, "Usage: /watch <dir>".to_string());
            return Some(false);
        }
        if !Path::new(directory).is_dir() {
            app.push_message(ChatMessage::error(format!(
                "Directory not found: {directory}"
            )));
            return Some(false);
        }
        if watch_state.is_running() {
            show_command_info_popup(
                app,
                raw,
                "Watch mode is already active. Use /unwatch first.".to_string(),
            );
            return Some(false);
        }

        let stop = Arc::new(AtomicBool::new(false));
        let watch_tx = watch_msg_sender(tx);
        let handle = watcher::spawn_watch_worker(
            directory.to_string(),
            "Explain the changes in these files".to_string(),
            watch_tx,
            stop.clone(),
        );

        watch_state.stop_flag = Some(stop);
        watch_state.handle = Some(handle);
        watch_state.directory = Some(directory.to_string());
        app.set_status(format!("Watching {directory} for changes"));
        return Some(false);
    }

    if lowered == "/unwatch" {
        if watch_state.is_running() {
            watch_state.stop();
            app.set_status("Watch mode stopped");
        } else {
            show_command_info_popup(app, raw, "No active watch task.".to_string());
        }
        return Some(false);
    }

    if lowered == "/plan-mode" {
        match rpc_toggle_config_blocking(rpc_cmd_tx, "plan_mode.enabled") {
            Ok(result) => {
                let enabled = result
                    .get("value")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(true);
                let message = if enabled {
                    "Plan mode enabled. The shared agent loop now injects plan-first guidance before execution, while mutating tools still go through preview and approval."
                } else {
                    "Plan mode disabled. Requests will use the normal execution loop without the extra plan-first guidance."
                };
                show_command_info_popup(app, raw, message.to_string());
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to toggle plan mode: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered.starts_with("/plan ") {
        const PLAN_REPLY_TIMEOUT_SECS: u64 = 130;

        let request = raw.split_once(' ').map(|x| x.1).unwrap_or("").trim().to_string();
        if request.is_empty() {
            show_command_info_popup(app, raw, "Usage: /plan <task description>".to_string());
            return Some(false);
        }
        let plan_prompt = format!(
            "Generate a step-by-step plan for the following task. \
Return ONLY a numbered list (1. step, 2. step, etc.) with no other text.\n\n\
Task: {request}"
        );
        app.plan.original_request = request.clone();
        app.push_message(ChatMessage::user(format!("/plan {request}")));
        app.start_waiting();
        let tx2 = tx.clone();
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        if rpc_cmd_tx
            .send(RpcCommand::ChatStreaming {
                message: plan_prompt,
                request_id: app.next_request_id(),
                context_files: Vec::new(),
                pinned_context_files: Vec::new(),
                context_budget_tokens: Some(app.context_budget_tokens),
                reply: reply_tx,
            })
            .is_err()
        {
            app.stop_waiting();
            app.push_message(ChatMessage::error(
                "Failed to send /plan request: RPC worker unavailable",
            ));
            return Some(false);
        }
        let request_clone = request.clone();
        thread::spawn(move || {
            match reply_rx.recv_timeout(Duration::from_secs(PLAN_REPLY_TIMEOUT_SECS)) {
                Ok(Ok(content)) => {
                    let steps: Vec<String> = content
                        .lines()
                        .filter(|l| {
                            let t = l.trim();
                            !t.is_empty()
                                && t.chars()
                                    .next()
                                    .map(|c| c.is_ascii_digit())
                                    .unwrap_or(false)
                        })
                        .map(|l| {
                            let t = l.trim();
                            t.find(". ")
                                .map(|i| t[i + 2..].to_string())
                                .unwrap_or_else(|| t.to_string())
                        })
                        .collect();
                    if steps.is_empty() {
                        let _ = tx2.send(ServerMsg::Error {
                            message: format!(
                                "Could not parse plan steps from response:\n{content}"
                            ),
                        });
                    } else {
                        let _ = tx2.send(ServerMsg::SystemMessage {
                            content: format!("__PLAN__:{request_clone}:{}", steps.join("\n")),
                        });
                    }
                }
                Ok(Err(e)) => {
                    let _ = tx2.send(ServerMsg::Error { message: e });
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "Timed out waiting for /plan response".into(),
                    });
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "RPC unavailable".into(),
                    });
                }
            }
        });
        return Some(false);
    }

    None
}
