use super::super::*;
use super::core::show_command_info_popup;

pub(super) fn handle_review_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    _watch_state: &mut WatchState,
    _qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered.starts_with("/review") {
        let maybe_path = raw.split_once(' ').map(|x| x.1)
            .map(str::trim)
            .filter(|s| !s.is_empty());

        let (language, code) = if let Some(path) = maybe_path {
            match rpc_read_file_blocking(rpc_cmd_tx, path) {
                Ok(content) => (detect_language_from_path(path).to_string(), content),
                Err(e) => {
                    app.push_message(ChatMessage::error(format!(
                        "Failed to read file for review: {e}"
                    )));
                    return Some(false);
                }
            }
        } else {
            match rpc_execute_command_blocking(rpc_cmd_tx, "git diff --staged") {
                Ok(diff) => ("diff".to_string(), diff),
                Err(e) => {
                    app.push_message(ChatMessage::error(format!(
                        "Unable to read staged diff: {e}"
                    )));
                    return Some(false);
                }
            }
        };

        if code.trim().is_empty() || code.trim() == "(No output)" {
            show_command_info_popup(app, raw, "Nothing to review.".to_string());
            return Some(false);
        }

        let prompt = build_review_prompt(&language, &code);
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            prompt,
            raw.to_string(),
            launch.session_log.as_ref(),
        );
        return Some(false);
    }

    if lowered == "/test" {
        show_command_info_popup(app, raw, "Usage: /test <file>".to_string());
        return Some(false);
    }

    if lowered.starts_with("/test ") {
        let file_path = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if file_path.is_empty() {
            show_command_info_popup(app, raw, "Usage: /test <file>".to_string());
            return Some(false);
        }

        let content = match rpc_read_file_blocking(rpc_cmd_tx, file_path) {
            Ok(content) => content,
            Err(e) => {
                app.push_message(ChatMessage::error(format!(
                    "Failed to read file for test generation: {e}"
                )));
                return Some(false);
            }
        };

        let prompt = build_test_prompt(detect_language_from_path(file_path), &content);
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            prompt,
            raw.to_string(),
            launch.session_log.as_ref(),
        );
        return Some(false);
    }

    if lowered == "/commit --apply-last" {
        if let Some(last) = last_assistant_message(app) {
            let subject = first_line(&last);
            if subject.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Last assistant response was empty; nothing to commit.".to_string(),
                );
                return Some(false);
            }

            let command = format!("git commit -m {}", shell_escape_single_quotes(&subject));
            match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
                Ok(output) => show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Commit executed with message: `{subject}`\n\n{}",
                        truncate_block(&output, 1200)
                    ),
                ),
                Err(e) => app.push_message(ChatMessage::error(format!("Commit failed: {e}"))),
            }
        } else {
            show_command_info_popup(
                app,
                raw,
                "No assistant response found to apply as commit message.".to_string(),
            );
        }
        return Some(false);
    }

    if lowered.starts_with("/commit --apply ") {
        let msg = raw.splitn(3, ' ').nth(2).map(str::trim).unwrap_or("");
        if msg.is_empty() {
            show_command_info_popup(app, raw, "Usage: /commit --apply <message>".to_string());
            return Some(false);
        }
        let command = format!("git commit -m {}", shell_escape_single_quotes(msg));
        match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
            Ok(output) => show_command_info_popup(
                app,
                raw,
                format!("Commit executed.\n\n{}", truncate_block(&output, 1200)),
            ),
            Err(e) => app.push_message(ChatMessage::error(format!("Commit failed: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/commit" {
        match rpc_execute_command_blocking(rpc_cmd_tx, "git diff --staged") {
            Ok(diff) => {
                if diff.trim().is_empty() || diff.trim() == "(No output)" {
                    show_command_info_popup(
                        app,
                        raw,
                        "No staged changes. Stage files with `git add` first.".to_string(),
                    );
                    return Some(false);
                }
                let prompt = build_commit_prompt(&diff);
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    prompt,
                    "/commit".to_string(),
                    launch.session_log.as_ref(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Unable to read staged diff: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered.starts_with("/diff") {
        let parts: Vec<&str> = raw.split_whitespace().collect();
        if parts.len() < 3 {
            show_command_info_popup(app, raw, "Usage: /diff <file1> <file2>".to_string());
            return Some(false);
        }

        match rpc_compare_files_blocking(rpc_cmd_tx, parts[1], parts[2]) {
            Ok(diff) => {
                if diff.trim() == "(No differences)" {
                    show_command_info_popup(app, raw, diff);
                } else {
                    app.push_message(ChatMessage::diff_view(
                        format!("{} vs {}", parts[1], parts[2]),
                        truncate_block(&diff, 20_000),
                    ));
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to compare files: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/explain-diff" || lowered.starts_with("/explain-diff ") {
        let target = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        let command = if target.is_empty() {
            "git diff".to_string()
        } else {
            format!("git diff -- {}", shell_escape_single_quotes(target))
        };
        match rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, &command, Some(60), 75) {
            Ok(diff) => {
                if diff.trim().is_empty() {
                    show_command_info_popup(app, raw, "No diff content found.".to_string());
                    return Some(false);
                }
                let prompt = format!(
                    "Analyze this git diff and produce:\n1) behavior changes\n2) regression risks\n3) missing tests\n4) quick validation steps.\n\n```diff\n{}\n```",
                    truncate_block(&diff, 12000)
                );
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    apply_response_mode_to_user_input(app.response_mode, &prompt),
                    raw.to_string(),
                    launch.session_log.as_ref(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to collect diff: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/fix-failures" || lowered.starts_with("/fix-failures ") {
        let command_hint = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        let failure_output = if !command_hint.is_empty() {
            match rpc_execute_command_with_timeout_blocking(
                rpc_cmd_tx,
                command_hint,
                Some(300),
                320,
            ) {
                Ok(output) => {
                    app.last_command_output = Some(output.clone());
                    output
                }
                Err(e) => {
                    app.push_message(ChatMessage::error(format!(
                        "Failed to run `{command_hint}`: {e}"
                    )));
                    return Some(false);
                }
            }
        } else if let Some(previous) = app.last_command_output.clone() {
            previous
        } else {
            show_command_info_popup(
                app,
                raw,
                "No recent command/test output found.\nRun `/fix-failures <test-or-lint-command>` or execute a command first.".to_string(),
            );
            return Some(false);
        };

        let prompt = format!(
            "Given this failure output, rank likely root causes and propose an efficient fix plan.\nInclude: immediate fix, verification command, and fallback options.\n\n```text\n{}\n```",
            truncate_block(&failure_output, 12000)
        );
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            apply_response_mode_to_user_input(app.response_mode, &prompt),
            raw.to_string(),
            launch.session_log.as_ref(),
        );
        return Some(false);
    }

    None
}
