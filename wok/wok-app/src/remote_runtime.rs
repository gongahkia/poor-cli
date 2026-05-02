//! Attached-session sync and remote-control runtime handlers.

use super::*;
use jsonrpc_params::RpcError;

impl WokHandler {
    pub(super) fn sync_attached_session_snapshot(&mut self) {
        let Some(session) = self.attached_session.as_deref() else {
            return;
        };

        let snapshot = match wok_app::daemon::snapshot_session(session) {
            Ok(snapshot) => snapshot,
            Err(error) => {
                warn!("failed to fetch daemon snapshot for session '{session}': {error}");
                return;
            }
        };

        let daemon_panes = snapshot.get("panes").and_then(Value::as_array);

        // iterate all local panes mapped to daemon panes
        let local_pane_ids: Vec<PaneId> = self.panes.keys().copied().collect();
        for local_pane_id in local_pane_ids {
            let daemon_pane_id = self.attached_daemon_pane_id(local_pane_id);

            let rows = daemon_panes
                .and_then(|panes| {
                    panes
                        .iter()
                        .find(|pane| {
                            pane.get("pane_id")
                                .and_then(Value::as_u64)
                                .is_some_and(|value| value == daemon_pane_id)
                        })
                        .and_then(|pane| pane.get("rows"))
                        .and_then(Value::as_array)
                })
                .or_else(|| {
                    if daemon_pane_id == 0 {
                        snapshot.get("rows").and_then(Value::as_array)
                    } else {
                        None
                    }
                });
            let Some(rows) = rows else {
                continue;
            };

            let Some(pane) = self.panes.get_mut(&local_pane_id) else {
                continue;
            };

            let mut latest_row = pane.daemon_last_synced_row;
            let mut new_lines = Vec::new();
            let mut reset_detected = false;
            for row in rows {
                let Some(absolute_row) = row.get("absolute_row").and_then(Value::as_u64) else {
                    continue;
                };
                let Some(text) = row.get("text").and_then(Value::as_str) else {
                    continue;
                };
                // detect reset: absolute_row went backwards
                if latest_row
                    .is_some_and(|latest| (absolute_row as usize) < latest.saturating_sub(100))
                {
                    reset_detected = true;
                }
                if reset_detected
                    || latest_row.map_or(true, |latest| absolute_row as usize > latest)
                {
                    new_lines.push(text.to_string());
                    latest_row = Some(absolute_row as usize);
                }
            }

            if reset_detected {
                pane.daemon_last_synced_row = None;
            }

            if !new_lines.is_empty() {
                pane.terminal.restore_scrollback(&new_lines);
                pane.daemon_last_synced_row = latest_row;
                self.needs_redraw = true;
            }
        }
    }

    pub(super) fn pump_remote_control(&mut self) {
        let requests = self
            .remote_control
            .as_mut()
            .map_or_else(Vec::new, RemoteControlServer::poll_requests);

        for request in requests {
            let response = self.handle_remote_request(&request);
            if let Some(payload) = response {
                if let Some(server) = self.remote_control.as_mut() {
                    server.send_response(request.client_id, &payload);
                }
            }
        }
    }

    fn handle_remote_request(&mut self, request: &RemoteRequest) -> Option<Value> {
        let response_id = request.id.clone();
        if request.method != "wok.get_rpc_info" && !self.remote_request_authenticated(request) {
            response_id.as_ref()?;
            return Some(error_response(
                response_id,
                -32001,
                "unauthorized: missing or invalid RPC auth token",
            ));
        }

        let result: Result<Value, RpcError> = match request.method.as_str() {
            "wok.get_rpc_info" => Ok(self.remote_get_rpc_info()),
            "wok.get_panes" => Ok(self.remote_get_panes()),
            "wok.send_text" => self.remote_send_text(&request.params),
            "wok.run_action" => self.remote_run_action(&request.params),
            "wok.get_blocks" => self.remote_get_blocks(&request.params),
            "wok.get_text" => self.remote_get_text(&request.params),
            "wok.get_git_status" => self.remote_get_git_status(&request.params),
            "wok.create_pane" => self.remote_create_pane(&request.params),
            "wok.close_pane" => self.remote_close_pane(&request.params),
            "wok.set_theme" => self.remote_set_theme(&request.params),
            "wok.notify" => self.remote_notify(&request.params),
            "wok.get_failure_summary" => self.remote_get_failure_summary(&request.params),
            "wok.get_failure_trends" => self.remote_get_failure_trends(&request.params),
            "wok.setup.init" => self.remote_setup_init(&request.params),
            "wok.setup.doctor" => self.remote_setup_doctor(&request.params),
            "wok.setup.reset" => self.remote_setup_reset(&request.params),
            "wok.setup.shell_install" => self.remote_setup_shell_install(&request.params),
            "wok.setup.shell_rollback" => self.remote_setup_shell_rollback(&request.params),
            _ => Err(RpcError::method_not_found(format!(
                "unknown method '{}'",
                request.method
            ))),
        };
        response_id.as_ref()?;
        Some(match result {
            Ok(payload) => result_response(response_id, payload),
            Err(rpc_err) => error_response(response_id, rpc_err.code, rpc_err.message),
        })
    }

    fn remote_request_authenticated(&self, request: &RemoteRequest) -> bool {
        let Some(expected) = self.remote_rpc_token.as_deref() else {
            return true;
        };
        request
            .auth_token
            .as_deref()
            .map(str::trim)
            .is_some_and(|token| !token.is_empty() && token == expected)
    }

    fn remote_get_rpc_info(&self) -> Value {
        json!({
            "schema_version": REMOTE_RPC_SCHEMA_VERSION,
            "methods": remote_rpc_methods(),
            "auth_required": self.remote_rpc_token.is_some(),
        })
    }

    fn remote_get_panes(&self) -> Value {
        let mut pane_ids = self.panes.keys().copied().collect::<Vec<_>>();
        pane_ids.sort_unstable();
        let active_pane = self.active_pane_id();
        Value::Array(
            pane_ids
                .into_iter()
                .filter_map(|pane_id| {
                    let pane = self.panes.get(&pane_id)?;
                    let tab_index = self.workspace.find_tab_index_for_pane(pane_id);
                    let tab = tab_index.and_then(|index| self.workspace.tabs.get(index));
                    Some(json!({
                        "pane_id": pane_id,
                        "tab_id": tab.map(|tab| tab.id),
                        "tab_index": tab_index,
                        "tab_title": tab.map(|tab| tab.title.clone()),
                        "active": active_pane == Some(pane_id),
                        "title": pane.terminal.title,
                        "shell": pane.app.config.shell.to_string(),
                        "cwd": pane.current_cwd.display().to_string(),
                        "cols": pane.cols,
                        "rows": pane.rows
                    }))
                })
                .collect(),
        )
    }

    fn remote_send_text(&mut self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::extract_pane_id(params)?;
        let text = jsonrpc_params::jsonrpc_string_param(params, 1, "text")
            .map_err(RpcError::invalid_params)?;
        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        };
        pane.terminal.send_input(text.as_bytes()).map_err(|error| {
            RpcError::server_error(format!("failed to write to pane {pane_id}: {error}"))
        })?;
        self.needs_redraw = true;
        Ok(json!({
            "ok": true,
            "pane_id": pane_id
        }))
    }

    fn remote_run_action(&mut self, params: &Value) -> Result<Value, RpcError> {
        let (action_name, action_params) = jsonrpc_params::extract_action_name(params)?;
        let normalized = action_parser::normalize_remote_action_name(&action_name);
        let Some(action) =
            action_parser::parse_remote_action_with_params(&normalized, action_params.as_ref())
        else {
            return Err(RpcError::server_error(format!(
                "unknown action '{action_name}'"
            )));
        };
        self.handle_action(action);
        Ok(json!({
            "ok": true,
            "action": normalized
        }))
    }

    fn remote_get_blocks(&self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::extract_pane_id(params)?;
        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        };

        Ok(Value::Array(
            pane.app
                .block_manager
                .blocks
                .iter()
                .map(|block| {
                    json!({
                        "id": block.id,
                        "command_text": block.command_text,
                        "output_start_row": block.output_start_row,
                        "output_end_row": block.output_end_row,
                        "exit_code": block.exit_code,
                        "duration_ms": block.duration.map(|duration| duration.as_millis() as u64),
                        "is_collapsed": block.is_collapsed,
                        "is_bookmarked": block.is_bookmarked,
                        "cwd": block.cwd.display().to_string(),
                        "git_branch": block.git_branch
                    })
                })
                .collect(),
        ))
    }

    fn remote_get_text(&self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::extract_pane_id(params)?;
        let (start_row, end_row) = jsonrpc_params::extract_row_range(params)?;
        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        };
        let total_rows = pane.terminal.state.total_rows();
        if total_rows == 0 {
            return Ok(Value::Array(Vec::new()));
        }

        let max_row = total_rows.saturating_sub(1);
        let start = start_row.min(max_row);
        let end = end_row.min(max_row);
        Ok(Value::Array(
            (start..=end)
                .map(|row| {
                    json!({
                        "row": row,
                        "text": pane.terminal.state.row_text(row)
                    })
                })
                .collect(),
        ))
    }

    fn remote_get_git_status(&self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::jsonrpc_optional_u64_param(params, 0, "pane_id")
            .or_else(|| self.active_pane_id())
            .ok_or_else(|| RpcError::server_error("no active pane"))?;
        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        };

        match wok_git::service::load_status(&pane.current_cwd) {
            Ok(snapshot) => Ok(json!({
                "pane_id": pane_id,
                "is_git_repo": true,
                "repo_root": snapshot.worktree_root.display().to_string(),
                "branch": snapshot.branch,
                "clean": snapshot.is_clean(),
                "files": snapshot.files.into_iter().map(|file| {
                    json!({
                        "path": file.path,
                        "old_path": file.old_path,
                        "index_status": file.index_status.to_string(),
                        "worktree_status": file.worktree_status.to_string(),
                        "status_text": file.status_text().to_string(),
                        "staged_status_text": file.staged_status_text().to_string(),
                        "unstaged_status_text": file.unstaged_status_text().to_string(),
                        "is_staged": file.is_staged(),
                        "is_unstaged": file.is_unstaged(),
                        "additions": file.additions,
                        "deletions": file.deletions,
                        "is_binary": file.is_binary,
                    })
                }).collect::<Vec<_>>(),
            })),
            Err(wok_git::service::GitServiceError::NotGitRepository(_)) => Ok(json!({
                "pane_id": pane_id,
                "is_git_repo": false,
                "repo_root": null,
                "branch": null,
                "clean": true,
                "files": [],
            })),
            Err(error) => Err(RpcError::server_error(format!(
                "failed to load git status: {error}"
            ))),
        }
    }

    fn remote_create_pane(&mut self, params: &Value) -> Result<Value, RpcError> {
        if self.window.is_none() {
            return Err(RpcError::server_error("window is not initialized yet"));
        }
        let direction = jsonrpc_params::jsonrpc_optional_string_param(params, 0, "direction")
            .unwrap_or_else(|| "vertical".to_string());
        let action = match direction.to_ascii_lowercase().as_str() {
            "vertical" => Action::SplitVertical,
            "horizontal" => Action::SplitHorizontal,
            "floating" => Action::NewFloatingPane,
            _ => {
                return Err(RpcError::invalid_params(format!(
                    "unsupported pane direction '{direction}'"
                )))
            }
        };
        let before = self.panes.keys().copied().collect::<HashSet<_>>();
        self.handle_action(action);
        let created = self
            .panes
            .keys()
            .copied()
            .find(|pane_id| !before.contains(pane_id));
        let Some(pane_id) = created else {
            return Err(RpcError::server_error("failed to create pane"));
        };
        Ok(json!({
            "pane_id": pane_id
        }))
    }

    fn remote_close_pane(&mut self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::extract_pane_id(params)?;
        if !self.panes.contains_key(&pane_id) {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        }
        if !self.workspace.focus_pane(pane_id) {
            return Err(RpcError::server_error(format!(
                "failed to focus pane {pane_id}"
            )));
        }
        let before = self.panes.len();
        self.handle_action(Action::CloseSplit);
        if self.panes.len() >= before {
            return Err(RpcError::server_error(
                "unable to close pane (likely last remaining pane)",
            ));
        }
        Ok(json!({
            "closed": pane_id
        }))
    }

    fn remote_set_theme(&mut self, params: &Value) -> Result<Value, RpcError> {
        let theme = jsonrpc_params::jsonrpc_string_param(params, 0, "theme")
            .or_else(|_| jsonrpc_params::jsonrpc_string_param(params, 0, "theme_name_or_path"))
            .map_err(RpcError::invalid_params)?;
        self.apply_theme_request(ThemeRequest::Load(theme.clone()));
        Ok(json!({
            "ok": true,
            "theme": theme
        }))
    }

    fn remote_notify(&mut self, params: &Value) -> Result<Value, RpcError> {
        let message = jsonrpc_params::jsonrpc_string_param(params, 0, "message")
            .map_err(RpcError::invalid_params)?;
        self.status_message = Some(message.clone());
        self.needs_redraw = true;
        Ok(json!({
            "ok": true,
            "message": message
        }))
    }

    fn remote_get_failure_summary(&self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::extract_pane_id(params)?;
        if !self.panes.contains_key(&pane_id) {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        }
        let summary = self.failure_summary_for_pane(pane_id, 10);
        Ok(Value::Array(
            summary
                .into_iter()
                .map(|item| {
                    json!({
                        "command": item.command,
                        "count": item.count,
                        "last_exit_code": item.last_exit_code,
                        "last_completed_at_ms": item.last_completed_at_ms,
                    })
                })
                .collect(),
        ))
    }

    fn remote_get_failure_trends(&self, params: &Value) -> Result<Value, RpcError> {
        let pane_id = jsonrpc_params::extract_pane_id(params)?;
        if !self.panes.contains_key(&pane_id) {
            return Err(RpcError::server_error(format!("pane {pane_id} not found")));
        }

        let bucket_ms = jsonrpc_params::jsonrpc_optional_u64_param(params, 1, "bucket_ms")
            .unwrap_or(DEFAULT_FAILURE_TREND_BUCKET_MS)
            .max(60_000);
        let limit = jsonrpc_params::jsonrpc_optional_u64_param(params, 2, "limit")
            .unwrap_or(24)
            .clamp(1, 250) as usize;

        let trends = self.failure_trends_for_pane(pane_id, bucket_ms, limit);
        Ok(Value::Array(
            trends
                .into_iter()
                .map(|item| {
                    json!({
                        "command": item.command,
                        "cwd": item.cwd,
                        "branch": item.branch,
                        "bucket_start_ms": item.bucket_start_ms,
                        "count": item.count,
                        "last_exit_code": item.last_exit_code,
                        "last_completed_at_ms": item.last_completed_at_ms,
                    })
                })
                .collect(),
        ))
    }

    fn remote_setup_init(&mut self, params: &Value) -> Result<Value, RpcError> {
        let overwrite =
            jsonrpc_params::jsonrpc_optional_bool_param(params, 0, "overwrite").unwrap_or(false);
        setup_ops::run_init(overwrite)
            .map_err(|error| RpcError::server_error(format!("setup init failed: {error}")))?;
        Ok(json!({
            "ok": true,
            "overwrite": overwrite,
        }))
    }

    fn remote_setup_doctor(&mut self, params: &Value) -> Result<Value, RpcError> {
        let json = jsonrpc_params::jsonrpc_optional_bool_param(params, 0, "json").unwrap_or(true);
        setup_ops::run_doctor(json)
            .map_err(|error| RpcError::server_error(format!("setup doctor failed: {error}")))?;
        Ok(json!({
            "ok": true,
            "json": json,
        }))
    }

    fn remote_setup_reset(&mut self, params: &Value) -> Result<Value, RpcError> {
        let scope = jsonrpc_params::jsonrpc_optional_string_param(params, 0, "scope")
            .unwrap_or_else(|| "managed".to_string());
        let yes = jsonrpc_params::jsonrpc_optional_bool_param(params, 1, "yes").unwrap_or(false);
        let scope_value = parse_reset_scope_value(&scope).ok_or_else(|| {
            RpcError::invalid_params(format!("unsupported reset scope '{scope}'"))
        })?;
        setup_ops::run_reset(scope_value, yes)
            .map_err(|error| RpcError::server_error(format!("setup reset failed: {error}")))?;
        Ok(json!({
            "ok": true,
            "scope": scope.to_ascii_lowercase(),
            "yes": yes,
        }))
    }

    fn remote_setup_shell_install(&mut self, params: &Value) -> Result<Value, RpcError> {
        let shell = jsonrpc_params::jsonrpc_optional_string_param(params, 0, "shell");
        let overwrite =
            jsonrpc_params::jsonrpc_optional_bool_param(params, 1, "overwrite").unwrap_or(false);
        setup_ops::run_shell_install(shell.as_deref(), overwrite).map_err(|error| {
            RpcError::server_error(format!("setup shell install failed: {error}"))
        })?;
        Ok(json!({
            "ok": true,
            "shell": shell,
            "overwrite": overwrite,
        }))
    }

    fn remote_setup_shell_rollback(&mut self, params: &Value) -> Result<Value, RpcError> {
        let shell = jsonrpc_params::jsonrpc_optional_string_param(params, 0, "shell");
        let yes = jsonrpc_params::jsonrpc_optional_bool_param(params, 1, "yes").unwrap_or(false);
        setup_ops::run_shell_rollback(shell.as_deref(), yes).map_err(|error| {
            RpcError::server_error(format!("setup shell rollback failed: {error}"))
        })?;
        Ok(json!({
            "ok": true,
            "shell": shell,
            "yes": yes,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request_with_token(token: Option<&str>) -> RemoteRequest {
        RemoteRequest {
            client_id: 1,
            id: Some(json!(1)),
            method: "wok.get_panes".to_string(),
            params: json!([]),
            auth_token: token.map(ToString::to_string),
        }
    }

    #[test]
    fn remote_request_authentication_is_optional_by_default() {
        let handler = WokHandler::new(WokConfig::default());
        assert!(handler.remote_request_authenticated(&request_with_token(None)));
    }

    #[test]
    fn remote_request_authentication_rejects_missing_or_invalid_tokens() {
        let mut handler = WokHandler::new(WokConfig::default());
        handler.remote_rpc_token = Some("top-secret".to_string());

        assert!(!handler.remote_request_authenticated(&request_with_token(None)));
        assert!(!handler.remote_request_authenticated(&request_with_token(Some("wrong-token"))));
        assert!(handler.remote_request_authenticated(&request_with_token(Some("top-secret"))));
    }

    #[test]
    fn remote_get_rpc_info_reports_methods_and_auth_requirement() {
        let mut handler = WokHandler::new(WokConfig::default());
        handler.remote_rpc_token = Some("secret".to_string());

        let info = handler.remote_get_rpc_info();
        assert_eq!(info["schema_version"], json!(REMOTE_RPC_SCHEMA_VERSION));
        assert_eq!(info["auth_required"], json!(true));
        let methods = info["methods"]
            .as_array()
            .expect("methods should be an array");
        assert!(methods.iter().any(|value| value == "wok.get_rpc_info"));
        assert!(methods
            .iter()
            .any(|value| value == "wok.setup.shell_rollback"));
    }

    #[test]
    fn handle_remote_request_rejects_unauthorized_requests() {
        let mut handler = WokHandler::new(WokConfig::default());
        handler.remote_rpc_token = Some("secret".to_string());

        let response = handler
            .handle_remote_request(&request_with_token(None))
            .expect("id requests should return an error response");
        assert_eq!(response["error"]["code"], json!(-32001));
    }

    #[test]
    fn handle_remote_request_allows_rpc_info_without_token() {
        let mut handler = WokHandler::new(WokConfig::default());
        handler.remote_rpc_token = Some("secret".to_string());
        let request = RemoteRequest {
            client_id: 1,
            id: Some(json!(1)),
            method: "wok.get_rpc_info".to_string(),
            params: json!([]),
            auth_token: None,
        };

        let response = handler
            .handle_remote_request(&request)
            .expect("id requests should return a response");
        assert_eq!(
            response["result"]["schema_version"],
            json!(REMOTE_RPC_SCHEMA_VERSION)
        );
        assert_eq!(response["result"]["auth_required"], json!(true));
    }
}
