use super::super::*;
use super::core::show_command_info_popup;
use super::context::{format_doctor_report_payload, format_status_view_payload, format_trust_view_payload};
use super::provider::{format_instruction_stack, format_mcp_status, format_policy_status, parse_mcp_tool_names};
use super::tasks::{format_runs_payload, format_workflow_detail};

pub(super) fn handle_system_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    _tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    _launch: &BackendLaunchContext,
    _cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered.starts_with("/run ") {
        let command = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if command.is_empty() {
            show_command_info_popup(app, raw, "Usage: /run <command>".to_string());
            return Some(false);
        }

        match rpc_execute_command_blocking(rpc_cmd_tx, command) {
            Ok(output) => {
                app.last_command_output = Some(output.clone());
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "**Command:** `{command}`\n\n{}",
                        truncate_block(&output, 1600)
                    ),
                )
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Command failed: {e}"))),
        }
        return Some(false);
    }

    if lowered.starts_with("/read ") {
        let file_path = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if file_path.is_empty() {
            show_command_info_popup(app, raw, "Usage: /read <file>".to_string());
            return Some(false);
        }

        match rpc_read_file_blocking(rpc_cmd_tx, file_path) {
            Ok(content) => {
                let language = detect_language_from_path(file_path);
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "File: `{file_path}`\n```{language}\n{}\n```",
                        truncate_block(&content, 3200)
                    ),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Read failed: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/pwd" {
        show_command_info_popup(app, raw, format!("Current directory: `{}`", app.cwd));
        return Some(false);
    }

    if lowered == "/ls" || lowered.starts_with("/ls ") {
        let path = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or(".");
        let command = format!("ls -la {}", shell_escape_single_quotes(path));
        match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
            Ok(output) => show_command_info_popup(
                app,
                raw,
                format!("**Listing:** `{path}`\n\n{}", truncate_block(&output, 1600)),
            ),
            Err(e) => app.push_message(ChatMessage::error(format!("ls failed: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/doctor" {
        match rpc_get_doctor_report_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                show_command_info_popup(app, raw, format_doctor_report_payload(&payload))
            }
            Err(error) => {
                show_command_info_popup(app, raw, format!("Failed to load doctor report: {error}"))
            }
        }
        return Some(false);
    }

    if lowered == "/trust" {
        match rpc_get_trust_view_blocking(rpc_cmd_tx) {
            Ok(payload) => show_command_info_popup(app, raw, format_trust_view_payload(&payload)),
            Err(error) => show_command_info_popup(app, raw, format!("Failed to load trust view: {error}")),
        }
        return Some(false);
    }

    if lowered == "/runs" || lowered.starts_with("/runs ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let limit = args
            .get(1)
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(20);
        match rpc_list_runs_blocking(rpc_cmd_tx, None, None, limit) {
            Ok(payload) => {
                show_command_info_popup(app, raw, format_runs_payload(&payload, "**Runs**"))
            }
            Err(error) => {
                show_command_info_popup(app, raw, format!("Failed to load runs: {error}"))
            }
        }
        return Some(false);
    }

    if lowered == "/workflow" || lowered.starts_with("/workflow ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let selected = args.get(1).copied().unwrap_or("").trim();
        if selected.is_empty() {
            match rpc_list_workflows_blocking(rpc_cmd_tx) {
                Ok(payload) => {
                    let workflows = payload.get("workflows").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                    if workflows.is_empty() {
                        show_command_info_popup(app, raw, "No workflows available.".to_string());
                    } else {
                        let recommended = payload.get("recommended").and_then(|v| v.as_str()).unwrap_or("");
                        let items: Vec<ListSelectorItem> = workflows.iter().map(|w| {
                            let name = w.get("name").and_then(|v| v.as_str()).unwrap_or("unknown");
                            let description = w.get("description").and_then(|v| v.as_str()).unwrap_or("");
                            let marker = if name == recommended { " (recommended)" } else { "" };
                            ListSelectorItem {
                                label: format!("{name}{marker}: {description}"),
                                value: name.to_string(),
                            }
                        }).collect();
                        app.open_list_selector(ListSelectorState {
                            title: "Workflows".to_string(),
                            items,
                            selected_idx: 0,
                            command_template: "/workflow {}".to_string(),
                            action_hint_override: None,
                        });
                    }
                }
                Err(error) => {
                    show_command_info_popup(app, raw, format!("Failed to load workflows: {error}"))
                }
            }
        } else {
            match rpc_get_workflow_blocking(rpc_cmd_tx, selected) {
                Ok(payload) => show_command_info_popup(app, raw, format_workflow_detail(&payload)),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to load workflow `{selected}`: {error}"),
                ),
            }
        }
        return Some(false);
    }

    if lowered == "/status" {
        match rpc_get_status_view_blocking(rpc_cmd_tx) {
            Ok(payload) => show_command_info_popup(
                app,
                raw,
                format_status_view_payload(&payload, app, watch_state, qa_watch_state),
            ),
            Err(error) => {
                show_command_info_popup(app, raw, format!("Failed to load session status: {error}"))
            }
        }
        return Some(false);
    }

    if lowered == "/permissions" || lowered.starts_with("/permissions ") {
        let usage = "Usage: /permissions\n       /permissions mode <default|acceptEdits|plan|bypassPermissions|dontAsk>\n       /permissions <default|acceptEdits|plan|bypassPermissions|dontAsk>\n       /permissions <allow|deny|ask> <tool> [pattern] [scope]\n       /permissions clear-session";
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() == 1 {
            match rpc_get_permissions_blocking(rpc_cmd_tx) {
                Ok(payload) => show_command_info_popup(app, raw, format_permissions_payload(&payload)),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to fetch permissions: {error}"),
                ),
            }
            return Some(false);
        }

        let subcommand = args[1].trim().to_ascii_lowercase();
        if subcommand == "clear-session" {
            match rpc_set_permissions_blocking(rpc_cmd_tx, None, None, true) {
                Ok(payload) => show_command_info_popup(app, raw, format_permissions_payload(&payload)),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to clear session rules: {error}"),
                ),
            }
            return Some(false);
        }

        let mut mode_override: Option<String> = None;
        if subcommand == "mode" {
            mode_override = args
                .get(2)
                .and_then(|value| normalize_permission_mode_input(value));
        } else if let Some(mode) = normalize_permission_mode_input(subcommand.as_str()) {
            mode_override = Some(mode);
        }

        if let Some(mode) = mode_override {
            match rpc_set_permissions_blocking(rpc_cmd_tx, Some(mode.as_str()), None, false) {
                Ok(payload) => show_command_info_popup(app, raw, format_permissions_payload(&payload)),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to set permission mode: {error}"),
                ),
            }
            return Some(false);
        }

        if matches!(subcommand.as_str(), "allow" | "deny" | "ask") {
            let tool_name = match args.get(2).copied().map(str::trim).filter(|value| !value.is_empty()) {
                Some(value) => value,
                None => {
                    show_command_info_popup(app, raw, usage.to_string());
                    return Some(false);
                }
            };
            let pattern = args.get(3).copied().unwrap_or("").trim();
            let scope = args.get(4).copied().unwrap_or("session").trim().to_ascii_lowercase();
            if !matches!(scope.as_str(), "session" | "local" | "project" | "user") {
                show_command_info_popup(
                    app,
                    raw,
                    "Scope must be one of: session, local, project, user".to_string(),
                );
                return Some(false);
            }
            let add_rule = serde_json::json!({
                "scope": scope,
                "toolName": tool_name,
                "behavior": subcommand,
                "ruleContent": pattern,
            });
            match rpc_set_permissions_blocking(rpc_cmd_tx, None, Some(add_rule), false) {
                Ok(payload) => show_command_info_popup(app, raw, format_permissions_payload(&payload)),
                Err(error) => show_command_info_popup(
                    app,
                    raw,
                    format!("Failed to save permission rule: {error}"),
                ),
            }
            return Some(false);
        }

        show_command_info_popup(app, raw, usage.to_string());
        return Some(false);
    }

    if lowered.starts_with("/permission-mode") {
        let maybe_mode = raw.split_whitespace().nth(1);
        if let Some(mode) = maybe_mode {
            let normalized = match normalize_permission_mode_input(mode) {
                Some(value) => value,
                None => {
                    app.push_message(ChatMessage::error(
                        "Invalid mode. Use one of: default, acceptEdits, plan, bypassPermissions, dontAsk".to_string(),
                    ));
                    return Some(false);
                }
            };
            if normalized.is_empty() {
                app.push_message(ChatMessage::error(
                    "Invalid mode. Use one of: default, acceptEdits, plan, bypassPermissions, dontAsk".to_string(),
                ));
                return Some(false);
            }

            match rpc_set_config_blocking(
                rpc_cmd_tx,
                "security.permission_mode",
                Value::String(normalized.clone()),
            ) {
                Ok(_) => show_command_info_popup(
                    app,
                    raw,
                    format!("Permission mode set to **{normalized}**"),
                ),
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to set permission mode: {e}"
                ))),
            }
            return Some(false);
        }

        match rpc_get_config_blocking(rpc_cmd_tx) {
            Ok(cfg) => {
                let current = cfg
                    .get("permissionMode")
                    .and_then(|v| v.as_str())
                    .unwrap_or("default");
                let modes = [
                    ("default", "ask before mutating actions"),
                    ("acceptEdits", "auto-approve file edits; prompt for commands"),
                    ("plan", "read-only planning mode"),
                    ("bypassPermissions", "skip all permission prompts"),
                    ("dontAsk", "suppress prompts for scripted sessions"),
                ];
                let items: Vec<ListSelectorItem> = modes.iter().map(|(name, desc)| {
                    let active = if *name == current { " (active)" } else { "" };
                    ListSelectorItem { label: format!("{name}{active}: {desc}"), value: name.to_string() }
                }).collect();
                app.open_list_selector(ListSelectorState {
                    title: "Permission Mode".to_string(), items, selected_idx: 0,
                    command_template: "/permission-mode {}".to_string(),
                    action_hint_override: None,
                });
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch permission mode: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/mcp" || lowered.starts_with("/mcp ") {
        let usage = "Usage: /mcp status\n       /mcp enable <server>\n       /mcp disable <server>\n       /mcp allow <server> <tool...>\n       /mcp deny <server> <tool...>\n       /mcp clear-allow <server>\n       /mcp clear-deny <server>";
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();

        if subcommand.is_empty() {
            let items = vec![
                ListSelectorItem { label: "status: Show MCP server status".into(), value: "status".into() },
                ListSelectorItem { label: "enable: Enable an MCP server".into(), value: "enable".into() },
                ListSelectorItem { label: "disable: Disable an MCP server".into(), value: "disable".into() },
                ListSelectorItem { label: "allow: Allow tools on a server".into(), value: "allow".into() },
                ListSelectorItem { label: "deny: Deny tools on a server".into(), value: "deny".into() },
                ListSelectorItem { label: "clear-allow: Clear allow list".into(), value: "clear-allow".into() },
                ListSelectorItem { label: "clear-deny: Clear deny list".into(), value: "clear-deny".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "MCP".into(), items, selected_idx: 0,
                command_template: "/mcp {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }

        if subcommand == "status" {
            match rpc_get_mcp_status_blocking(rpc_cmd_tx) {
                Ok(payload) => show_command_info_popup(app, raw, format_mcp_status(&payload)),
                Err(error) => {
                    show_command_info_popup(app, raw, format!("MCP status failed: {error}"))
                }
            }
            return Some(false);
        }

        let server = match args
            .get(2)
            .copied()
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            Some(server) => server,
            None => {
                show_command_info_popup(app, raw, usage.to_string());
                return Some(false);
            }
        };

        let key_path = match subcommand.as_str() {
            "enable" | "disable" => format!("mcp_servers.{server}.enabled"),
            "allow" | "clear-allow" => format!("mcp_servers.{server}.allow_tools"),
            "deny" | "clear-deny" => format!("mcp_servers.{server}.deny_tools"),
            _ => {
                show_command_info_popup(app, raw, usage.to_string());
                return Some(false);
            }
        };

        let value = match subcommand.as_str() {
            "enable" => Value::Bool(true),
            "disable" => Value::Bool(false),
            "clear-allow" | "clear-deny" => Value::Array(Vec::new()),
            "allow" | "deny" => {
                let tail = raw.splitn(4, ' ').nth(3).map(str::trim).unwrap_or("");
                let tools = parse_mcp_tool_names(tail);
                if tools.is_empty() {
                    show_command_info_popup(
                        app,
                        raw,
                        format!("Usage: /mcp {subcommand} <server> <tool...>"),
                    );
                    return Some(false);
                }
                Value::Array(tools)
            }
            _ => Value::Null,
        };

        match rpc_set_config_blocking(rpc_cmd_tx, &key_path, value) {
            Ok(_) => match rpc_get_mcp_status_blocking(rpc_cmd_tx) {
                Ok(payload) => show_command_info_popup(app, raw, format_mcp_status(&payload)),
                Err(_) => app.set_status(format!("Updated MCP config for `{server}`")),
            },
            Err(error) => {
                show_command_info_popup(app, raw, format!("Failed to update MCP config: {error}"))
            }
        }
        return Some(false);
    }

    if lowered == "/mcp-health" {
        match rpc_mcp_health_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let msg = serde_json::to_string_pretty(&payload).unwrap_or_else(|_| format!("{payload:?}"));
                show_command_info_popup(app, raw, format!("MCP Health Check:\n{msg}"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("MCP health check failed: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/tools" {
        match rpc_get_tools_blocking(rpc_cmd_tx) {
            Ok(value) => {
                let tools = value
                    .get("tools")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();

                if tools.is_empty() {
                    show_command_info_popup(
                        app,
                        raw,
                        "No tool declarations returned by backend.".to_string(),
                    );
                    return Some(false);
                }

                let mut lines = Vec::new();
                lines.push("**Available Tools:**".to_string());
                lines.push(String::new());

                for tool in tools {
                    let name = tool
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown-tool");
                    let desc = tool
                        .get("description")
                        .and_then(|v| v.as_str())
                        .unwrap_or("No description");
                    lines.push(format!("- **{name}**: {desc}"));
                }

                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch tools: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/instructions" || lowered.starts_with("/instructions ") {
        let referenced_files = raw
            .split_whitespace()
            .skip(1)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>();
        match rpc_get_instruction_stack_blocking(rpc_cmd_tx, &referenced_files) {
            Ok(payload) => show_command_info_popup(app, raw, format_instruction_stack(&payload)),
            Err(error) => show_command_info_popup(
                app,
                raw,
                format!("Failed to inspect instruction stack: {error}"),
            ),
        }
        return Some(false);
    }

    if lowered == "/policy" || lowered.starts_with("/policy ") {
        match rpc_get_policy_status_blocking(rpc_cmd_tx) {
            Ok(payload) => show_command_info_popup(app, raw, format_policy_status(&payload)),
            Err(error) => show_command_info_popup(
                app,
                raw,
                format!("Failed to inspect policy status: {error}"),
            ),
        }
        return Some(false);
    }

    if lowered == "/memory" || lowered.starts_with("/memory ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();
        let usage = "Usage: /memory\n       /memory show\n       /memory edit\n       /memory set <text>\n       /memory append <text>\n       /memory clear";

        if subcommand.is_empty() {
            let items = vec![
                ListSelectorItem { label: "show: Display repo memory".into(), value: "show".into() },
                ListSelectorItem { label: "edit: Edit repo memory".into(), value: "edit".into() },
                ListSelectorItem { label: "set: Replace repo memory".into(), value: "set".into() },
                ListSelectorItem { label: "append: Append to repo memory".into(), value: "append".into() },
                ListSelectorItem { label: "clear: Clear repo memory".into(), value: "clear".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "Memory".into(), items, selected_idx: 0,
                command_template: "/memory {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }

        if subcommand == "show" {
            match load_repo_memory(app) {
                Ok(Some(content)) if !content.trim().is_empty() => show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "**Repo Memory**\n\n```markdown\n{}\n```",
                        truncate_block(&content, 5000)
                    ),
                ),
                Ok(_) => show_command_info_popup(
                    app,
                    raw,
                    "Repo memory is empty.\nUse `/memory set <text>` or `/memory append <text>`."
                        .to_string(),
                ),
                Err(error) => app.push_message(ChatMessage::error(error)),
            }
            return Some(false);
        }

        if subcommand == "edit" {
            let path = repo_memory_path(app);
            if !path.exists() {
                match save_repo_memory(app, "") {
                    Ok(_) => {}
                    Err(error) => {
                        app.push_message(ChatMessage::error(error));
                        return Some(false);
                    }
                }
            }
            match open_file_in_editor(path.to_string_lossy().as_ref()) {
                Ok(()) => app.set_status(format!("Opened `{}`", path.display())),
                Err(error) => app.push_message(ChatMessage::error(error)),
            }
            return Some(false);
        }

        if subcommand == "clear" {
            match save_repo_memory(app, "") {
                Ok(path) => show_command_info_popup(
                    app,
                    raw,
                    format!("Cleared repo memory at `{}`.", path.display()),
                ),
                Err(error) => app.push_message(ChatMessage::error(error)),
            }
            return Some(false);
        }

        if subcommand == "set" || subcommand == "append" {
            let payload = args.get(2).copied().unwrap_or("").trim();
            if payload.is_empty() {
                show_command_info_popup(app, raw, usage.to_string());
                return Some(false);
            }
            let next_content = if subcommand == "set" {
                payload.to_string()
            } else {
                match load_repo_memory(app) {
                    Ok(Some(existing)) if !existing.trim().is_empty() => {
                        format!("{}\n\n{}", existing.trim_end(), payload)
                    }
                    Ok(_) => payload.to_string(),
                    Err(error) => {
                        app.push_message(ChatMessage::error(error));
                        return Some(false);
                    }
                }
            };
            match save_repo_memory(app, &next_content) {
                Ok(path) => show_command_info_popup(
                    app,
                    raw,
                    format!("Updated repo memory at `{}`.", path.display()),
                ),
                Err(error) => app.push_message(ChatMessage::error(error)),
            }
            return Some(false);
        }

        show_command_info_popup(app, raw, usage.to_string());
        return Some(false);
    }

    None
}

fn format_permissions_payload(payload: &Value) -> String {
    let mode = payload
        .get("permissionMode")
        .and_then(|value| value.as_str())
        .unwrap_or("default");
    let preset = payload
        .get("sandboxPreset")
        .and_then(|value| value.as_str())
        .unwrap_or("workspace-write");

    let mut lines = vec![
        "**Permissions**".to_string(),
        format!("- Mode: `{mode}`"),
        format!("- Sandbox preset: `{preset}`"),
        String::new(),
    ];

    let rules = payload.get("rules").and_then(|value| value.as_object());
    if rules.is_none() {
        lines.push("No permission rules found.".to_string());
        return lines.join("\n");
    }

    for scope in ["session", "local", "project", "user"] {
        lines.push(format!("### {} rules", scope));
        let entries = rules
            .and_then(|map| map.get(scope))
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if entries.is_empty() {
            lines.push("- (none)".to_string());
            lines.push(String::new());
            continue;
        }
        for entry in entries {
            let behavior = entry
                .get("behavior")
                .and_then(|value| value.as_str())
                .unwrap_or("ask");
            let tool_name = entry
                .get("toolName")
                .and_then(|value| value.as_str())
                .unwrap_or("*");
            let rule_content = entry
                .get("ruleContent")
                .and_then(|value| value.as_str())
                .unwrap_or("");
            if rule_content.is_empty() {
                lines.push(format!("- `{behavior}` `{tool_name}`"));
            } else {
                lines.push(format!("- `{behavior}` `{tool_name}` when `{rule_content}`"));
            }
        }
        lines.push(String::new());
    }

    lines.join("\n")
}

fn normalize_permission_mode_input(raw: &str) -> Option<String> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "default" => Some("default".to_string()),
        "acceptedits" | "accept-edits" | "accept_edits" => Some("acceptEdits".to_string()),
        "plan" => Some("plan".to_string()),
        "bypasspermissions" | "bypass-permissions" | "bypass_permissions" => {
            Some("bypassPermissions".to_string())
        }
        "dontask" | "dont-ask" | "dont_ask" => Some("dontAsk".to_string()),
        "prompt" => Some("prompt".to_string()),
        "auto-safe" => Some("auto-safe".to_string()),
        "danger-full-access" => Some("danger-full-access".to_string()),
        _ => None,
    }
}
